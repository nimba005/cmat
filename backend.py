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

    # News table
    c.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT,
            image TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            posted_by TEXT
        )
    """)

    # Users table (single definition)
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'mp'
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

    # Survey table
    c.execute("""
        CREATE TABLE IF NOT EXISTS survey_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            indicator TEXT NOT NULL,
            value TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # Projects table
    c.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            image TEXT,
            latitude REAL,
            longitude REAL,
            start_date TEXT,
            end_date TEXT,
            budget REAL,
            status TEXT,
            completion_percentage REAL
        )
    """)

    conn.commit()
    conn.close()


def get_news():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, title, content, image, created_at, posted_by FROM news ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "content": r[2], "image": r[3], "created_at": r[4], "posted_by": r[5]} for r in rows]

def get_news_by_id(news_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, title, content, image, created_at, posted_by FROM news WHERE id=?", (news_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0],
            "title": row[1],
            "content": row[2],
            "image": row[3],
            "created_at": row[4],
            "posted_by": row[5]
        }
    return None

def add_news(title, content, image, posted_by):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO news (title, content, image, posted_by) VALUES (?, ?, ?, ?)", 
              (title, content, image, posted_by))
    conn.commit()
    conn.close()
    return True

def delete_news(news_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM news WHERE id=?", (news_id,))
    conn.commit()
    conn.close()
    return True



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

def prepare_graph_data(data: dict):
    """
    Transform extracted budget data into structures usable for frontend graphs.
    """

    graphs = {}

    # --- Graph 1: Allocated figures per project ---
    projects = data.get("Climate Projects", [])
    graphs["projects"] = [
        {"Programme": p["Programme"], "Allocated": sum(v for k, v in p.items() if isinstance(v, (int, float)))}
        for p in projects
    ]

    # --- Graph 2: Programmes vs Climate Projects ---
    total_budget = data.get("Total Budget", 0)
    sector_total = sum(v for v in (data.get("Sectors") or {}).values() if v)
    projects_total = sum(sum(v for k, v in p.items() if isinstance(v, (int, float))) for p in projects)

    graphs["categories"] = [
        {"Category": "Sectors", "Total": sector_total},
        {"Category": "Climate Projects", "Total": projects_total},
        {"Category": "Unallocated", "Total": max(total_budget - (sector_total + projects_total), 0)}
    ]

    # --- Graph 3: Yearly Comparisons (2022 vs 2023 vs 2024) ---
    yearly_totals = {"2022": 0, "2023": 0, "2024": 0}
    for p in projects:
        for year in yearly_totals.keys():
            if year in p and isinstance(p[year], (int, float)):
                yearly_totals[year] += p[year]

    graphs["yearly"] = [{"Year": int(y), "Total": yearly_totals[y]} for y in yearly_totals]

    return graphs




def create_user(username, password, role="mp"):
    """Register a new user with hashed password + role (default MP)."""
    hashed = bcrypt.generate_password_hash(password).decode("utf-8")
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                  (username, hashed, role))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False  # username exists


def verify_user(username, password):
    """
    Check username + password against DB.
    Returns the user's role if valid, otherwise None.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT password, role FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    if row and bcrypt.check_password_hash(row[0], password):
        return row[1]  # return role
    return None


def get_user_id(username):
    """Fetch user_id for a given username."""
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


def get_projects():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM projects")
    rows = c.fetchall()
    conn.close()

    return [
        {
            "id": r[0],
            "title": r[1],
            "description": r[2],
            "image": r[3],
            "latitude": r[4],
            "longitude": r[5],
            "start_date": r[6],
            "end_date": r[7],
            "budget": r[8],
            "status": r[9],
            "completion_percentage": r[10]
        }
        for r in rows
    ]


def add_project(title, description, image, latitude, longitude, start_date, end_date, budget, status, completion_percentage):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO projects (title, description, image, latitude, longitude, start_date, end_date, budget, status, completion_percentage)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (title, description, image, latitude, longitude, start_date, end_date, budget, status, completion_percentage))
    conn.commit()
    conn.close()
    return True


def update_project(project_id, title, description, image, latitude, longitude, start_date, end_date, budget, status, completion_percentage):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE projects
        SET title=?, description=?, image=?, latitude=?, longitude=?, start_date=?, end_date=?, budget=?, status=?, completion_percentage=?
        WHERE id=?
    """, (title, description, image, latitude, longitude, start_date, end_date, budget, status, completion_percentage, project_id))
    conn.commit()
    conn.close()
    return True


def delete_project(project_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM projects WHERE id=?", (project_id,))
    conn.commit()
    conn.close()
    return True




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

def _extract_json_from_text(s: str):
    """Try to find the first JSON object in a string and parse it."""
    if not s:
        return None
    # find first { and last } that likely form the JSON block
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = s[start:end+1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # try minor fixes: remove code fences and trailing commas
        candidate = re.sub(r"```json|```", "", candidate)
        candidate = re.sub(r",\s*}", "}", candidate)
        candidate = re.sub(r",\s*]", "]", candidate)
        try:
            return json.loads(candidate)
        except Exception:
            return None

def ai_extract_budget_info(text: str):
    """
    Uses AI to analyze PDF text and extract structured budget data.
    Returns a dict (may contain nested dicts/lists) or {} on failure.
    """
    prompt = f"""
    You are a financial data analyst. From the following budget document, extract structured data.

    Return ONLY a valid JSON object with this structure:

    {{
        "Total Budget": <number>,
        "Sectors": {{
            "Energy": <number>,
            "Agriculture": <number>,
            "Health": <number>,
            "Transport": <number>,
            "Water": <number>
        }},
        "Climate Projects": [
            {{"Programme": "PIDACC Zambezi", "2024": 123456, "2023": 98765}},
        ]
    }}

    Rules:
    - Return only JSON (no surrounding explanation). If you include text wrap it away.
    - Use numbers (no commas) for numeric fields.
    - Use null if not present.

    Document text:
    {text}
    """

    # Try OpenAI with rotation
    for _ in range(max(1, len(API_KEYS))):
        try:
            client = get_client()
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a financial data analyst."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0
            )
            content = None
            # robustly extract content
            try:
                content = response.choices[0].message.get("content") or response.choices[0].message["content"]
            except Exception:
                # try older/alternate fields
                content = getattr(response.choices[0], "text", None)

            parsed = _extract_json_from_text(content or "")
            if parsed:
                return parsed
            else:
                print("⚠️ OpenAI returned text but no JSON could be extracted. Raw snippet:", (content or "")[:300])
                # continue to fallback or next key
                continue
        except (RateLimitError, AuthenticationError) as e:
            print("⚠️ OpenAI key failed, rotating...", e)
            # rotate will be handled in get_client() on next call
            continue
        except Exception as e:
            print("⚠️ OpenAI extraction error:", e)
            break

    # Fallback: DeepSeek
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
        reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = _extract_json_from_text(reply or "")
        if parsed:
            return parsed
        else:
            print("⚠️ DeepSeek returned non-JSON or JSON not parsable. Raw reply stored.")
            return {"raw_reply": reply}
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
def _clean_recursive(obj):
    """Recursively convert numeric-like strings into floats for dicts/lists, leave nested dicts intact."""
    if obj is None:
        return None
    if isinstance(obj, (int, float)):
        return float(obj)
    if isinstance(obj, str):
        return clean_numeric_value(obj)
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            out[k] = _clean_recursive(v)
        return out
    if isinstance(obj, list):
        return [_clean_recursive(x) for x in obj]
    return obj

def extract_combined_budget_info(text: str):
    """
    Merge AI-extracted structured budget info with keyword-based extraction.
    Ensures important fields like Total Budget, sector allocations, adaptation, mitigation, etc. are captured.
    """
    ai_results = ai_extract_budget_info(text) or {}
    keyword_results = extract_numbers_from_text(
        text,
        keywords=[
            "total budget",
            "total public investment in climate initiatives",
            "percentage of national budget allocated to climate adaptation",
            "private sector investment mobilized",
            "adaptation",
            "mitigation",
            "energy",
            "agriculture",
            "health",
            "transport",
            "water"
        ]
    )

    # Start with AI results (may be nested)
    merged = {}

    # copy ai output, cleaning recursively
    for k, v in ai_results.items():
        merged[k] = _clean_recursive(v)

    # Map fuzzy keyword matches to structured labels (only when not present)
    mapping = {
        "total": "Total Budget",
        "adaptation": "Adaptation",
        "mitigation": "Mitigation",
        "public": "Public",
        "energy": "Sectors",
        "agriculture": "Sectors",
        "health": "Sectors",
        "transport": "Sectors",
        "water": "Sectors"
    }

    # If keywords found, inject into merged (without overwriting present data)
    for k, v in keyword_results.items():
        clean_key = k.lower().strip()
        for kw, label in mapping.items():
            if kw in clean_key:
                if label == "Sectors":
                    # make sure merged has nested Sectors dict
                    merged.setdefault("Sectors", {})
                    # use the keyword (e.g., 'energy') to assign its numeric
                    merged["Sectors"][kw.capitalize()] = _clean_recursive(v)
                else:
                    if label not in merged or merged.get(label) is None:
                        merged[label] = _clean_recursive(v)
                break

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

