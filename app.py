from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Problem

app = Flask(__name__)
app.secret_key = "sigrafilm-secret"

# Connessione DB - su Render puoi sovrascrivere con la variabile d'ambiente DATABASE_URL
app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://sigrafilm_db_user:aTaxodWqw29ViddgvGpzT21EGjME4AHM@dpg-d31i59m3jp1c73fu9efg-a.frankfurt-postgres.render.com/sigrafilm_db"
db.init_app(app)

@app.before_first_request
def create_tables():
    db.create_all()
    if not User.query.filter_by(username="admin").first():
        admin = User(username="admin", password_hash=generate_password_hash("SigraFilm2025"), role="admin")
        db.session.add(admin)
        db.session.commit()

@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("dashboard"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form["username"]).first()
        if user and check_password_hash(user.password_hash, request.form["password"]):
            session["user_id"] = user.id
            session["role"] = user.role
            return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    problems = Problem.query.all()
    return render_template("dashboard.html", problems=problems)

@app.route("/admin/users", methods=["GET", "POST"])
def admin_users():
    if session.get("role") != "admin":
        return "Accesso negato"
    if request.method == "POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"])
        new_user = User(username=username, password_hash=password, role="user")
        db.session.add(new_user)
        db.session.commit()
    users = User.query.all()
    return render_template("users.html", users=users)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
