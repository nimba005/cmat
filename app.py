from flask import Flask, render_template, request, jsonify, session, redirect, flash, send_from_directory
import backend

app = Flask(__name__)
app.secret_key = "supersecretkey"  # change to env variable in production

# ------------------ NAVIGATION ROUTES ------------------
@app.route("/")
def home():
    return render_template("index.html", page="home")

@app.route("/about")
def about():
    projects = [
        {
            "title": "Chisamba Solar Power Plant (100 MW)",
            "desc": "Commissioned June 2025; helps diversify Zambia’s energy mix away from hydropower.",
            "img": "images/chisamba.jpg"
        },
        {
            "title": "Itimpi Solar Power Station (60 MW)",
            "desc": "Kitwe-based solar farm addressing electricity shortages, commissioned April 2024.",
            "img": "images/itimpi.jpg"
        },
        {
            "title": "Zambia Riverside Solar Power Station (34 MW)",
            "desc": "Expanded solar farm in Kitwe operational since February 2023.",
            "img": "images/riverside.jpg"
        },
        {
            "title": "Growing Greener Project (Simalaha Conservancy)",
            "desc": "Community-led project building resilience, combating desertification and boosting biodiversity.",
            "img": "images/greener.jpg"
        },
        {
            "title": "Strengthening Climate Resilience in the Barotse Sub-basin",
            "desc": "CIF/World Bank-supported effort (2013–2022) to enhance local adaptation capacity.",
            "img": "images/barotse.jpg"
        },
        {
            "title": "Early Warning Systems Project",
            "desc": "UNDP-GEF initiative building Zambia’s hydro-meteorological monitoring infrastructure.",
            "img": "images/earlywarning.jpg"
        },
        {
            "title": "National Adaptation Programme of Action (NAPA)",
            "desc": "Targeted adaptation interventions prioritizing vulnerable sectors.",
            "img": "images/napa.jpg"
        },
        {
            "title": "NDC Implementation Framework",
            "desc": "₮17.2 B Blueprint (2023–2030) aligning mitigation/adaptation with national development goals.",
            "img": "images/ndc.jpg"
        }
    ]
    return render_template("index.html", page="about", projects=projects)


# ------------------ DOCS ROUTE ------------------
@app.route("/docs/<path:filename>")
def download_file(filename):
    return send_from_directory("docs", filename)


@app.route("/upload", methods=["GET"])
def upload_page():
    if "user" not in session:
        return redirect("/login")
    return render_template("index.html", page="upload")


@app.route("/survey")
def survey():
    if "user" not in session:
        return redirect("/login")
    print("DEBUG: survey route reached!")   # ✅ add this
    survey_data = backend.get_survey_data(session["user"])
    return render_template(
        "index.html",
        page="survey",
        survey_data=survey_data,
        indicators=backend.CMAT_INDICATORS
    )



@app.route("/calendar")
def calendar():
    if "user" not in session:
        return redirect("/login")
    return render_template("index.html", page="calendar")

@app.route("/api/events", methods=["GET", "POST"])
def events_api():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    if request.method == "POST":
        data = request.json
        title = data.get("title")
        start = data.get("start")
        end = data.get("end")
        if not all([title, start, end]):
            return jsonify({"error": "Missing fields"}), 400
        success = backend.add_event(session["user"], title, start, end)
        return jsonify({"success": success})

    # GET events
    events = backend.get_events(session["user"])
    return jsonify(events)

@app.route("/api/events/<int:event_id>", methods=["DELETE"])
def delete_event(event_id):
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    success = backend.delete_event(session["user"], event_id)
    return jsonify({"success": success})

@app.route("/api/survey", methods=["GET", "POST"])
def survey_api():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    if request.method == "POST":
        data = request.json
        success = backend.save_survey_data(session["user"], data)

        # Process survey into results (like /upload)
        results = backend.process_survey_results(data)

        return jsonify({"success": success, "results": results})

    # GET → return saved survey values
    data = backend.get_survey_data(session["user"])
    return jsonify(data)



# ------------------ AUTH ROUTES ------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if backend.create_user(username, password):
            session["user"] = username
            flash("Signup successful! You are now logged in.", "success")
            return redirect("/")
        else:
            flash("Username already exists.", "error")
            return render_template("index.html", page="signup")
    return render_template("index.html", page="signup")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if backend.verify_user(username, password):
            session["user"] = username
            flash("Login successful!", "success")
            return redirect("/")
        else:
            flash("Invalid credentials.", "error")
            return render_template("index.html", page="login")
    return render_template("index.html", page="login")


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/")


# ------------------ API: FILE UPLOAD ------------------
@app.route("/upload", methods=["POST"])
def upload():
    if "pdf" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["pdf"]
    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    # Extract text from PDF
    text = backend.extract_text_from_pdf(file)

    # Extract budgets (combined)
    budget_info = backend.extract_combined_budget_info(text)

    # Extract agriculture budget
    agri_df, agri_totals = backend.extract_agriculture_budget(text)

    # Extract climate programmes
    climate_df = backend.extract_climate_programmes(text)

    # Extract total budget
    total_budget = backend.extract_total_budget(text)

    response = {
        "budget_info": budget_info,
        "agriculture": agri_df.to_dict(orient="records") if agri_df is not None else None,
        "agriculture_totals": agri_totals,
        "climate_programmes": climate_df.to_dict(orient="records") if climate_df is not None else None,
        "total_budget": total_budget,
    }

    # ✅ Save extracted budget_info into survey DB
    if "user" in session and budget_info:
        backend.save_survey_data(session["user"], budget_info)

    return jsonify(response)

@app.route("/api/chat", methods=["POST"])
def chat():
    user_message = request.json.get("message")
    if not user_message:
        return jsonify({"error": "Message required"}), 400

    # Build system prompt
    system_prompt = (
        "You are a helpful assistant specialized in climate policy, "
        "finance, and adaptation in Zambia. Always give clear, accurate, "
        "and structured answers."
    )

    # --- Try OpenAI first ---
    try:
        client = backend.get_client()   # ✅ FIXED: use the correct function
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.4
        )
        reply = response.choices[0].message["content"]
        return jsonify({"reply": reply})
    except Exception as e:
        print("⚠️ OpenAI chat failed, falling back to DeepSeek:", e)

    # --- Fallback: DeepSeek ---
    try:
        import requests, os
        deepseek_key = os.getenv("DEEPSEEK_API_KEY")
        if not deepseek_key:
            return jsonify({"error": "No DeepSeek API key configured"}), 500

        headers = {"Authorization": f"Bearer {deepseek_key}", "Content-Type": "application/json"}
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.4
        }

        r = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        print("DEBUG DeepSeek response:", data)  # ✅ add this to inspect format

        # Safely extract reply
        reply = data.get("choices", [{}])[0].get("message", {}).get("content", "⚠️ No reply content")
        return jsonify({"reply": reply})
    except Exception as e:
        print("❌ DeepSeek chat failed:", e)
        return jsonify({"error": "Both OpenAI and DeepSeek failed"}), 500





# ------------------ RUN APP ------------------
if __name__ == "__main__":
    app.run(debug=True)
