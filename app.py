from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from backend import (
    CMAT_INDICATORS,
    extract_text_from_pdf,
    extract_numbers_from_text,
    bar_chart,
    radar_chart,
    extract_agriculture_budget,
    agriculture_bar_chart,
    extract_climate_programmes,
    climate_bar_chart,
    extract_total_budget,
    climate_multi_year_chart,
    climate_2024_vs_total_chart
)
import os, json
import plotly.io as pio

app = Flask(__name__)
app.secret_key = "super-secret-key"
USER_FILE = "users.json"

# ---------------- User Helpers ----------------
def load_users():
    return json.load(open(USER_FILE)) if os.path.exists(USER_FILE) else {"admin": "admin"}

def save_users(users):
    json.dump(users, open(USER_FILE, "w"))

# ---------------- Routes ----------------
@app.route("/")
def home():
    return render_template("index.html", page="home", logged_in=session.get("logged_in", False), user=session.get("current_user"))

@app.route("/login", methods=["GET", "POST"])
def login():
    users = load_users()
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        if username in users and users[username] == password:
            session["logged_in"] = True
            session["current_user"] = username
            return redirect(url_for("home"))
        return render_template("index.html", page="login", error="Invalid credentials")
    return render_template("index.html", page="login")

@app.route("/signup", methods=["POST"])
def signup():
    users = load_users()
    username = request.form["username"]
    password = request.form["password"]
    if username in users:
        return render_template("index.html", page="login", error="⚠️ Username exists")
    users[username] = password
    save_users(users)
    return render_template("index.html", page="login", message="✅ Account created. Please log in.")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/upload", methods=["POST"])
def upload():
    if "pdf" not in request.files:
        return jsonify({"error": "No file uploaded"})
    file = request.files["pdf"]
    text = extract_text_from_pdf(file, max_pages=10)

    # Data extraction
    climate_df = extract_climate_programmes(text)
    total_budget = extract_total_budget(text)
    agriculture_df, totals = extract_agriculture_budget(text)
    extracted = extract_numbers_from_text(text)

    # Convert charts to JSON for rendering with Plotly.js
    charts = {}
    if climate_df is not None:
        charts["climate_multi"] = pio.to_json(climate_multi_year_chart(climate_df, total_budget=total_budget))
        charts["climate_vs_total"] = pio.to_json(climate_2024_vs_total_chart(climate_df, total_budget=total_budget))
    if agriculture_df is not None:
        charts["agriculture"] = pio.to_json(agriculture_bar_chart(agriculture_df, totals, year=2024))
    if extracted:
        numeric_results = {k: v for k, v in extracted.items() if isinstance(v, (int, float))}
        if numeric_results:
            charts["bar"] = pio.to_json(bar_chart(numeric_results, "Budget Indicators"))
            charts["radar"] = pio.to_json(radar_chart(numeric_results, "Composite View"))

    return jsonify({
        "text": text[:3000],
        "climate": climate_df.to_dict(orient="records") if climate_df is not None else None,
        "total_budget": total_budget,
        "agriculture": agriculture_df.to_dict(orient="records") if agriculture_df is not None else None,
        "agriculture_totals": totals,
        "extracted": extracted,
        "charts": charts
    })

@app.route("/survey", methods=["POST"])
def survey():
    results = request.json
    numeric_results = {k: float(v) for k, v in results.items() if v}
    charts = {}
    if numeric_results:
        charts["bar"] = pio.to_json(bar_chart(numeric_results, "Indicator Values"))
        charts["radar"] = pio.to_json(radar_chart(numeric_results, "Composite View"))
    return jsonify({"charts": charts})

if __name__ == "__main__":
    app.run(debug=True)
