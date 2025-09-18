import fitz  # PyMuPDF
import pandas as pd
import re
import json
import os
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError, AuthenticationError
import sqlite3
from flask_bcrypt import Bcrypt
import requests

bcrypt = Bcrypt()

DB_PATH = "cmat.db"

def init_db():
    """Initialize SQLite database with required tables."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Users table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    # Events table
    c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            start TEXT NOT NULL,
            end TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # ✅ Survey table
    c.execute("""
        CREATE TABLE IF NOT EXISTS survey_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            indicator TEXT NOT NULL,
            value TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


def save_survey_data(username, data):
    """Save survey responses (dict of indicator:value)."""
    user_id = get_user_id(username)
    if not user_id:
        return False

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Remove old entries for clean overwrite
    c.execute("DELETE FROM survey_data WHERE user_id=?", (user_id,))
    for indicator, value in data.items():
        c.execute("INSERT INTO survey_data (user_id, indicator, value) VALUES (?, ?, ?)",
                  (user_id, indicator, value))
    conn.commit()
    conn.close()
    return True


def get_survey_data(username):
    """Fetch saved survey data for user."""
    user_id = get_user_id(username)
    if not user_id:
        return {}
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT indicator, value FROM survey_data WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}

def process_survey_results(data: dict):
    """
    Take raw survey responses and return results in the same format as /upload.
    """
    cleaned = {k: clean_numeric_value(v) for k, v in data.items() if v}

    # Build the same response shape as /upload
    response = {
        "budget_info": cleaned,
        "agriculture": None,           # you could later extend to specific categories
        "agriculture_totals": None,
        "climate_programmes": None,
        "total_budget": cleaned.get("Total Budget"),
    }
    return response



def create_user(username, password):
    """Register a new user with hashed password."""
    hashed = bcrypt.generate_password_hash(password).decode("utf-8")
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False  # username exists

def verify_user(username, password):
    """Check username + password against DB."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT password FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    if row and bcrypt.check_password_hash(row[0], password):
        return True
    return False


def get_user_id(username):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def add_event(username, title, start, end):
    user_id = get_user_id(username)
    if not user_id:
        return False
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO events (user_id, title, start, end) VALUES (?, ?, ?, ?)",
              (user_id, title, start, end))
    conn.commit()
    conn.close()
    return True


def get_events(username):
    user_id = get_user_id(username)
    if not user_id:
        return []
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, title, start, end FROM events WHERE user_id = ?", (user_id,))
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "start": r[2], "end": r[3]} for r in rows]

def delete_event(username, event_id):
    """Delete an event if it belongs to the given username."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Find user_id for the username
    c.execute("SELECT id FROM users WHERE username=?", (username,))
    user = c.fetchone()
    if not user:
        conn.close()
        return False

    user_id = user[0]

    # Delete only if the event belongs to this user
    c.execute("DELETE FROM events WHERE id=? AND user_id=?", (event_id, user_id))
    conn.commit()
    deleted = c.rowcount > 0  # True if any row was deleted
    conn.close()
    return deleted




# Load environment variables
load_dotenv()
print("DEBUG: OPENAI_API_KEY_1 loaded?", bool(os.getenv("OPENAI_API_KEY_1")))
print("DEBUG: OPENAI_API_KEY_2 loaded?", bool(os.getenv("OPENAI_API_KEY_2")))
print("DEBUG: DEEPSEEK_API_KEY loaded?", bool(os.getenv("DEEPSEEK_API_KEY")))

# ---- CMAT Indicators ----
CMAT_INDICATORS = {
    "Finance": ["Total Budget", "Public", "Adaptation", "Mitigation"],
    "Sectors": ["Energy", "Agriculture", "Health", "Transport", "Water"],
}

# ---- OpenAI Client Setup ----
API_KEYS = [
    os.getenv("OPENAI_API_KEY_1"),
    os.getenv("OPENAI_API_KEY_2")
]

# ---- DeepSeek Key ----
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY")

current_key_index = 0
client = OpenAI(api_key=API_KEYS[current_key_index])

def get_client():
    """
    Returns a working OpenAI client.
    If quota/auth errors happen, rotate to the next key.
    """
    global client, current_key_index
    try:
        return client
    except (RateLimitError, AuthenticationError):
        current_key_index = (current_key_index + 1) % len(API_KEYS)
        if API_KEYS[current_key_index]:
            client = OpenAI(api_key=API_KEYS[current_key_index])
            print(f"⚠️ Switched to backup OpenAI key #{current_key_index+1}")
            return client
        else:
            raise AuthenticationError("No valid OpenAI keys available.")
    

# ---- PDF Extraction ----
def extract_text_from_pdf(uploaded_file, max_pages=None):
    """
    Extracts raw text from a PDF file object.
    """
    text = []
    with fitz.open(stream=uploaded_file.read(), filetype="pdf") as doc:
        for page_num, page in enumerate(doc):
            if max_pages and page_num >= max_pages:
                break
            text.append(page.get_text("text") or "")
    return "\n".join(text)

# ---- AI Extraction ----
def ai_extract_budget_info(text: str):
    """
    Uses AI to analyze PDF text and extract structured budget data.
    1. Try OpenAI (rotating keys if needed).
    2. If all OpenAI keys fail, fallback to DeepSeek.
    """
    prompt = f"""
    You are a financial data analyst. Extract budget allocations for climate-related programmes
    (Energy, Agriculture, Health, Transport, Water, and total budget).
    Return results as a clean JSON object with numeric values only.
    Text: {text[:3000]}
    """
    # --- Try OpenAI ---
    for _ in range(len(API_KEYS)):
        try:
            client = get_openai_client()
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a financial data analyst."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0
            )
            content = response.choices[0].message["content"]
            return json.loads(content)
        except (RateLimitError, AuthenticationError) as e:
            print("⚠️ OpenAI key failed, rotating...", e)
            # rotate and retry
            continue
        except Exception as e:
            print("⚠️ OpenAI extraction error:", e)
            break  # break to fallback

    # --- Fallback: DeepSeek ---
    try:
        deepseek_key = os.getenv("DEEPSEEK_API_KEY")
        if not deepseek_key:
            print("❌ No DeepSeek API key configured.")
            return {}

        headers = {"Authorization": f"Bearer {deepseek_key}", "Content-Type": "application/json"}
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "You are a financial data analyst."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0
        }

        r = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception as e:
        print("❌ DeepSeek extraction failed:", e)
        return {}

# ---- Helper: Clean numbers ----
def clean_numeric_value(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        cleaned = re.sub(r"[^\d\.\-]", "", val)
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None

# ---- Combined AI + Keyword Extraction ----
def extract_combined_budget_info(text: str):
    ai_results = ai_extract_budget_info(text) or {}
    keyword_results = extract_numbers_from_text(
        text,
        keywords=[
            "total public investment in climate initiatives",
            "percentage of national budget allocated to climate adaptation",
            "private sector investment mobilized", 
            "energy", "agriculture", "health", "transport", "water"
        ]
    )

    merged = ai_results.copy()
    mapping = {
        "total": "Total Budget",
        "adaptation": "Adaptation",
        "public": "Public",
        "energy": "Energy",
        "agriculture": "Agriculture",
        "health": "Health",
        "transport": "Transport",
        "water": "Water"
    }

    for k, v in keyword_results.items():
        clean_key = k.lower().strip()
        mapped_key = None
        for kw, label in mapping.items():
            if kw in clean_key:
                mapped_key = label
                break
        if mapped_key and mapped_key not in merged:
            merged[mapped_key] = v

    merged = {k: clean_numeric_value(v) for k, v in merged.items() if v is not None}
    return merged

# ---- Agriculture Budget ----
def extract_agriculture_budget(text: str):
    rows = []
    pattern = re.compile(
        r"(?P<programme>[A-Za-z\s\-\(\)]+)\s+\d+\s+(?P<budget2024>[\d,]+)\s+(?P<budget2023>[\d,]+)\s+(?P<budget2022>[\d,]+)"
    )

    for match in pattern.finditer(text):
        prog = match.group("programme").strip()
        if "agric" in prog.lower():
            rows.append({
                "Programme": prog,
                "2024": float(match.group("budget2024").replace(",", "")),
                "2023": float(match.group("budget2023").replace(",", "")),
                "2022": float(match.group("budget2022").replace(",", "")),
            })

    df = pd.DataFrame(rows)
    if df.empty:
        return None, None

    totals = df[["2022", "2023", "2024"]].sum().to_dict()
    return df, totals

# ---- Climate Programmes ----
def extract_climate_programmes(text: str):
    rows = []
    climate_codes = {
        "07": "Irrigation Development",
        "17": "Irrigation Development Support Programme",
        "18": "Farming Systems / SCRALA",
        "41": "Chiansi Water Development Project",
        "61": "Programme for Adaptation of Climate Change (PIDACC) Zambezi",
    }

    clean_text = re.sub(r"\s+", " ", text)

    for code, name in climate_codes.items():
        pattern = re.compile(rf"\b{code}\b\s+([\d,]+)\s+([\d,]+).*?([\d,]+)")
        match = pattern.search(clean_text)
        if match:
            try:
                budget2022 = float(match.group(1).replace(",", ""))
                budget2023 = float(match.group(2).replace(",", ""))
                budget2024 = float(match.group(3).replace(",", ""))
            except ValueError:
                continue

            rows.append({
                "Programme": f"{code} - {name}",
                "2023": budget2023,
                "2024": budget2024
            })

    df = pd.DataFrame(rows)
    return df if not df.empty else None

def extract_total_budget(text: str):
    # look for "Total" followed by digits (ignore if no number)
    pattern = re.compile(r"Total[^0-9]*([\d,]+)", re.IGNORECASE)
    matches = pattern.findall(text)
    numbers = []
    for m in matches:
        try:
            numbers.append(float(m.replace(",", "")))
        except ValueError:
            continue
    return max(numbers) if numbers else None


# ---- Simple Number Extractor ----
def extract_numbers_from_text(text, keywords=None):
    results = {}
    if not text:
        return results

    if not keywords:
        keywords = ["total budget", "public", "adaptation", "mitigation"]

    clean_text = text.lower()
    for key in keywords:
        pattern = rf"{key}[^0-9]*([\d,\.]+)"
        match = re.search(pattern, clean_text)
        if match:
            num_str = match.group(1).replace(",", "")
            try:
                results[key] = float(num_str)
            except ValueError:
                results[key] = None
    return results

# Initialize DB on startup
init_db()

