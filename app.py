from flask import Flask, render_template, request, jsonify, session, redirect, flash, send_from_directory, url_for
import backend
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "supersecretkey"  # change to env variable in production


# ------------------ NAVIGATION ROUTES ------------------
@app.route("/admin/news")
def admin_news():
    if "user" not in session or session.get("role") != "admin":
        return redirect("/login")
    news = backend.get_news()
    return render_template("index.html", page="admin_news", news=news)

@app.route("/admin/news/add", methods=["POST"])
def add_news():
    if "user" not in session or session.get("role") != "admin":
        return redirect("/login")

    title = request.form.get("title")
    content = request.form.get("content")
    image_file = request.files.get("image")

    image_path = None
    if image_file:
        from werkzeug.utils import secure_filename
        filename = secure_filename(image_file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        image_file.save(filepath)
        image_path = f"images/{filename}"

    backend.add_news(title, content, image_path, session["user"])
    flash("✅ News posted successfully!", "success")
    return redirect(url_for("admin_news"))

@app.route("/admin/news/delete/<int:news_id>", methods=["POST"])
def delete_news(news_id):
    if "user" not in session or session.get("role") != "admin":
        return redirect("/login")
    backend.delete_news(news_id)
    flash("🗑️ News deleted", "info")
    return redirect(url_for("admin_news"))

@app.route("/news/<int:news_id>")
def news_detail(news_id):
    news_item = backend.get_news_by_id(news_id)
    if not news_item:
        return "❌ News not found", 404
    return render_template("index.html", page="news_detail", news=news_item)



@app.route("/")
def home():
    news = backend.get_news()   # ✅ fetch from DB
    return render_template("index.html", page="home", news=news)


@app.route("/about")
def about():
    # ✅ Fetch projects from database instead of hardcoding
    projects = backend.get_projects()
    return render_template("index.html", page="about", projects=projects)


@app.route("/api/projects")
def api_projects():
    # ✅ API endpoint that returns projects as JSON (for AJAX, maps, etc.)
    return jsonify(backend.get_projects())

# ✅ Configure uploads folder for project images
UPLOAD_FOLDER = os.path.join("static", "images")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/admin/projects")
def admin_projects():
    if "user" not in session:
        return redirect("/login")
    if session.get("role") != "admin":
        flash("🚫 Access denied: Admins only", "error")
        return redirect("/")
    projects = backend.get_projects()
    return render_template("index.html", page="admin_projects", projects=projects)



@app.route("/admin/projects/add", methods=["POST"])
def add_project():
    title = request.form.get("title")
    description = request.form.get("description")
    budget = float(request.form.get("budget") or 0)
    status = request.form.get("status")
    latitude = float(request.form.get("latitude") or 0)
    longitude = float(request.form.get("longitude") or 0)
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")
    completion_percentage = float(request.form.get("completion_percentage") or 0)

    image_file = request.files.get("image")
    if image_file and allowed_file(image_file.filename):
        filename = secure_filename(image_file.filename)
        image_file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        image_path = f"images/{filename}"   # ✅ stored relative to /static
    else:
        image_path = "images/default.jpg"   # fallback image

    # ✅ Save to your backend DB
    backend.add_project(
        title,
        description,
        image_path,
        latitude,
        longitude,
        start_date,
        end_date,
        budget,
        status,
        completion_percentage
    )

    flash("✅ Project added successfully!", "success")
    return redirect(url_for("admin_projects"))



@app.route("/admin/projects/update/<int:project_id>", methods=["POST"])
def update_project(project_id):
    title = request.form.get("title")
    description = request.form.get("description")
    budget = float(request.form.get("budget") or 0)
    status = request.form.get("status")
    latitude = float(request.form.get("latitude") or 0)
    longitude = float(request.form.get("longitude") or 0)
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")
    completion_percentage = float(request.form.get("completion_percentage") or 0)

    # ✅ Allow updating image if a new one is uploaded
    image_file = request.files.get("image")
    if image_file and allowed_file(image_file.filename):
        filename = secure_filename(image_file.filename)
        image_file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        image_path = f"images/{filename}"
    else:
        image_path = request.form.get("current_image")  # keep old if none uploaded

    backend.update_project(
        project_id,
        title,
        description,
        image_path,
        latitude,
        longitude,
        start_date,
        end_date,
        budget,
        status,
        completion_percentage
    )
    flash("✅ Project updated successfully!", "success")
    return redirect(url_for("admin_projects"))


@app.route("/admin/projects/delete/<int:project_id>", methods=["POST"])
def delete_project(project_id):
    backend.delete_project(project_id)
    flash("🗑️ Project deleted!", "info")
    return redirect(url_for("admin_projects"))




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
        role = request.form.get("role")  # NEW
        if backend.create_user(username, password, role):
            session["user"] = username
            session["role"] = role
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
        role = backend.verify_user(username, password)
        if role:
            session["user"] = username
            session["role"] = role
            flash(f"Login successful! Welcome {role.title()}", "success")
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

    # 3️⃣ Build response
    response = {
        "total_budget": budget_info.get("Total Budget"),
        "budget_info": budget_info,   # sector allocations
        "climate_programmes": budget_info.get("Climate Projects"),
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
