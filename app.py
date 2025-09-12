from flask import Flask, render_template, request, jsonify, session, redirect, flash
import backend

app = Flask(__name__)
app.secret_key = "supersecretkey"  # change to env variable in production

# ------------------ NAVIGATION ROUTES ------------------
@app.route("/")
def home():
    return render_template("index.html", page="home")

@app.route("/about")
def about():
    return render_template("index.html", page="about")

@app.route("/upload", methods=["GET"])
def upload_page():
    if "user" not in session:
        return redirect("/login")
    return render_template("index.html", page="upload")

@app.route("/survey")
def survey():
    if "user" not in session:
        return redirect("/login")
    return render_template("index.html", page="survey")

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

    return jsonify(response)

# ------------------ RUN APP ------------------
if __name__ == "__main__":
    app.run(debug=True)
