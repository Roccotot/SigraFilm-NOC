import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import create_engine, text
from datetime import datetime

app = Flask(__name__)

# ==========================
# CONFIGURAZIONE
# ==========================
APP_SECRET = os.environ.get("APP_SECRET", "dev-secret-change-me")
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///sigrafilm.db")

# Normalizza URL per psycopg2
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+psycopg2://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

# Engine SQLAlchemy
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)

app.config["SECRET_KEY"] = APP_SECRET

# ==========================
# SCHEMI SQL
# ==========================
SCHEMA_SQL_POSTGRES = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user','admin')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS issues (
    id SERIAL PRIMARY KEY,
    room TEXT NOT NULL,
    cinema TEXT NOT NULL,
    kind TEXT NOT NULL,
    description TEXT NOT NULL,
    urgency TEXT NOT NULL CHECK (urgency IN ('Non urgente','Sala ferma','Urgente')),
    status TEXT NOT NULL DEFAULT 'In corso',
    author_id INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);
"""

def init_db():
    with engine.begin() as conn:
        dialect = engine.url.get_backend_name()
        if dialect == "sqlite":
            conn.exec_driver_sql("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user','admin')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.exec_driver_sql("""
                CREATE TABLE IF NOT EXISTS issues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room TEXT NOT NULL,
                    cinema TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    description TEXT NOT NULL,
                    urgency TEXT NOT NULL CHECK(urgency IN ('Non urgente','Sala ferma','Urgente')),
                    status TEXT NOT NULL DEFAULT 'In corso',
                    author_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP,
                    FOREIGN KEY(author_id) REFERENCES users(id)
                )
            """)
        else:  # Postgres
            conn.exec_driver_sql(SCHEMA_SQL_POSTGRES)

        # Crea admin se non esiste
        exists = conn.execute(
            text("SELECT 1 FROM users WHERE username=:u LIMIT 1"),
            {"u": "admin"},
        ).first()
        if not exists:
            conn.execute(
                text("INSERT INTO users(username, password_hash, role) VALUES (:u, :p, 'admin')"),
                {"u": "admin", "p": generate_password_hash("SigraFilm2025")},
            )

with app.app_context():
    init_db()

# ==========================
# ROUTES
# ==========================

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

# ----- Login / Logout -----
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        with engine.connect() as conn:
            user = conn.execute(
                text("SELECT * FROM users WHERE username=:u"),
                {"u": username}
            ).mappings().first()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            flash("Login eseguito", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Credenziali non valide", "danger")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logout eseguito", "info")
    return redirect(url_for("login"))

# ----- Dashboard -----
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    with engine.connect() as conn:
        if session.get("role") == "admin":
            issues = conn.execute(text("SELECT issues.*, users.username FROM issues JOIN users ON issues.author_id=users.id ORDER BY created_at DESC")).mappings().all()
        else:
            issues = conn.execute(text("SELECT * FROM issues WHERE author_id=:a ORDER BY created_at DESC"), {"a": session["user_id"]}).mappings().all()

    return render_template("dashboard.html", issues=issues)

# ----- Crea nuovo problema -----
@app.route("/issues/new", methods=["GET", "POST"])
def new_issue():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        room = request.form["room"]
        cinema = request.form["cinema"]
        kind = request.form["kind"]
        description = request.form["description"]
        urgency = request.form["urgency"]

        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO issues(room, cinema, kind, description, urgency, author_id) VALUES (:r,:c,:k,:d,:u,:a)"),
                {"r": room, "c": cinema, "k": kind, "d": description, "u": urgency, "a": session["user_id"]},
            )

        flash("Problema inserito", "success")
        return redirect(url_for("dashboard"))

    return render_template("edit_issue.html", issue=None)

# ----- Modifica problema -----
@app.route("/issues/<int:issue_id>/edit", methods=["GET", "POST"])
def edit_issue(issue_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    with engine.connect() as conn:
        issue = conn.execute(text("SELECT * FROM issues WHERE id=:i"), {"i": issue_id}).mappings().first()

    if not issue:
        flash("Problema non trovato", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        room = request.form["room"]
        cinema = request.form["cinema"]
        kind = request.form["kind"]
        description = request.form["description"]
        urgency = request.form["urgency"]
        status = request.form["status"]

        with engine.begin() as conn:
            conn.execute(
                text("""UPDATE issues SET room=:r, cinema=:c, kind=:k, description=:d, urgency=:u, status=:s, updated_at=:up WHERE id=:i"""),
                {"r": room, "c": cinema, "k": kind, "d": description, "u": urgency, "s": status, "up": datetime.now(), "i": issue_id},
            )

        flash("Problema aggiornato", "success")
        return redirect(url_for("dashboard"))

    return render_template("edit_issue.html", issue=issue)

# ----- Cancella problema -----
@app.route("/issues/<int:issue_id>/delete", methods=["POST"])
def delete_issue(issue_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM issues WHERE id=:i"), {"i": issue_id})

    flash("Problema cancellato", "info")
    return redirect(url_for("dashboard"))

# ----- Admin: gestione utenti -----
@app.route("/admin/users")
def admin_users():
    if session.get("role") != "admin":
        return redirect(url_for("dashboard"))

    with engine.connect() as conn:
        users = conn.execute(text("SELECT * FROM users ORDER BY created_at DESC")).mappings().all()

    return render_template("admin_users.html", users=users)

@app.route("/admin/users/new", methods=["GET", "POST"])
def new_user():
    if session.get("role") != "admin":
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        role = request.form["role"]

        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO users(username, password_hash, role) VALUES (:u,:p,:r)"),
                {"u": username, "p": generate_password_hash(password), "r": role},
            )

        flash("Utente creato", "success")
        return redirect(url_for("admin_users"))

    return render_template("edit_user.html", user=None)

@app.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
def edit_user(user_id):
    if session.get("role") != "admin":
        return redirect(url_for("dashboard"))

    with engine.connect() as conn:
        user = conn.execute(text("SELECT * FROM users WHERE id=:i"), {"i": user_id}).mappings().first()

    if not user:
        flash("Utente non trovato", "danger")
        return redirect(url_for("admin_users"))

    if request.method == "POST":
        username = request.form["username"]
        role = request.form["role"]
        password = request.form["password"]

        with engine.begin() as conn:
            if password:
                conn.execute(
                    text("UPDATE users SET username=:u, role=:r, password_hash=:p WHERE id=:i"),
                    {"u": username, "r": role, "p": generate_password_hash(password), "i": user_id},
                )
            else:
                conn.execute(
                    text("UPDATE users SET username=:u, role=:r WHERE id=:i"),
                    {"u": username, "r": role, "i": user_id},
                )

        flash("Utente aggiornato", "success")
        return redirect(url_for("admin_users"))

    return render_template("edit_user.html", user=user)

@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
def delete_user(user_id):
    if session.get("role") != "admin":
        return redirect(url_for("dashboard"))

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE id=:i"), {"i": user_id})

    flash("Utente eliminato", "info")
    return redirect(url_for("admin_users"))

# ==========================
# RUN (solo locale)
# ==========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
