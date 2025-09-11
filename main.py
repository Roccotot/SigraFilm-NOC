import os
from flask import Flask, render_template, request, redirect, url_for, session as flask_session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from werkzeug.security import generate_password_hash, check_password_hash
from models import Base, User, Issue

# Flask app
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "super-secret-key")

# DB URL da Render (variabile d’ambiente consigliata)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://sigrafilm_db_user:aTaxodWqw29ViddgvGpzT21EGjME4AHM@dpg-d31i59m3jp1c73fu9efg-a.frankfurt-postgres.render.com/sigrafilm_db"
)

# Engine SQLAlchemy
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

# Crea le tabelle se non esistono
with engine.begin() as conn:
    Base.metadata.create_all(bind=conn)

# ------------------- ROUTES -------------------

@app.route("/")
def home():
    if "user_id" not in flask_session:
        return redirect(url_for("login"))
    return redirect(url_for("dashboard"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        db = SessionLocal()
        username = request.form["username"]
        password = request.form["password"]

        user = db.query(User).filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            flask_session["user_id"] = user.id
            flask_session["role"] = user.role
            db.close()
            return redirect(url_for("dashboard"))

        db.close()
        return "Credenziali non valide", 401

    return render_template("login.html")

@app.route("/logout")
def logout():
    flask_session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
def dashboard():
    if "user_id" not in flask_session:
        return redirect(url_for("login"))

    db = SessionLocal()
    issues = db.query(Issue).all()
    db.close()
    return render_template("dashboard.html", issues=issues)

# ------------------- ADMIN -------------------

@app.route("/admin/users")
def admin_users():
    if flask_session.get("role") != "admin":
        return "Accesso negato", 403

    db = SessionLocal()
    users = db.query(User).all()
    db.close()
    return render_template("admin_users.html", users=users)

@app.route("/admin/users/create", methods=["POST"])
def create_user():
    if flask_session.get("role") != "admin":
        return "Accesso negato", 403

    db = SessionLocal()
    username = request.form["username"]
    password = request.form["password"]
    role = request.form["role"]

    new_user = User(
        username=username,
        password_hash=generate_password_hash(password),
        role=role,
    )
    db.add(new_user)
    db.commit()
    db.close()
    return redirect(url_for("admin_users"))

@app.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
def edit_user(user_id):
    if flask_session.get("role") != "admin":
        return "Accesso negato", 403

    db = SessionLocal()
    user = db.query(User).filter_by(id=user_id).first()

    if request.method == "POST":
        user.username = request.form["username"]
        if request.form["password"]:
            user.password_hash = generate_password_hash(request.form["password"])
        user.role = request.form["role"]
        db.commit()
        db.close()
        return redirect(url_for("admin_users"))

    db.close()
    return render_template("edit_user.html", user=user)

# ------------------- ISSUES -------------------

@app.route("/issues/create", methods=["POST"])
def create_issue():
    if "user_id" not in flask_session:
        return redirect(url_for("login"))

    db = SessionLocal()
    new_issue = Issue(
        room=request.form["room"],
        cinema=request.form["cinema"],
        kind=request.form["kind"],
        description=request.form["description"],
        urgency=request.form["urgency"],
        author_id=flask_session["user_id"],
    )
    db.add(new_issue)
    db.commit()
    db.close()
    return redirect(url_for("dashboard"))

@app.route("/issues/<int:issue_id>/edit", methods=["GET", "POST"])
def edit_issue(issue_id):
    if "user_id" not in flask_session:
        return redirect(url_for("login"))

    db = SessionLocal()
    issue = db.query(Issue).filter_by(id=issue_id).first()

    if request.method == "POST":
        issue.room = request.form["room"]
        issue.cinema = request.form["cinema"]
        issue.kind = request.form["kind"]
        issue.description = request.form["description"]
        issue.urgency = request.form["urgency"]
        issue.status = request.form["status"]
        db.commit()
        db.close()
        return redirect(url_for("dashboard"))

    db.close()
    return render_template("edit_issue.html", issue=issue)

# ------------------- START -------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
