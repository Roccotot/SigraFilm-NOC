import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import create_engine, text

app = Flask(__name__)

# Secret per sessioni
APP_SECRET = os.environ.get("APP_SECRET", "dev-secret-change-me")
app.config["SECRET_KEY"] = APP_SECRET

# DB URL da Render
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///sigrafilm.db")

# Normalizza postgres URL
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+psycopg2://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

# SQLAlchemy engine
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)

# Schema Postgres
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
    """Crea tabelle e admin"""
    with engine.begin() as conn:
        dialect = engine.url.get_backend_name()
        if dialect == "sqlite":
            # SQLite: statement separati
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
        else:
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

# Inizializza db
with app.app_context():
    init_db()

# ----------------- ROUTES -------------------

@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("dashboard"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        with engine.begin() as conn:
            user = conn.execute(
                text("SELECT * FROM users WHERE username=:u"), {"u": username}
            ).mappings().first()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("dashboard"))
        else:
            flash("Credenziali non valide", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    with engine.begin() as conn:
        if session.get("role") == "admin":
            issues = conn.execute(text("SELECT issues.*, users.username FROM issues JOIN users ON users.id=issues.author_id ORDER BY created_at DESC")).mappings().all()
        else:
            issues = conn.execute(text("SELECT * FROM issues WHERE author_id=:a ORDER BY created_at DESC"), {"a": session["user_id"]}).mappings().all()

    return render_template("dashboard.html", issues=issues)

@app.route("/issue/new", methods=["GET","POST"])
def new_issue():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO issues(room, cinema, kind, description, urgency, author_id) VALUES (:r,:c,:k,:d,:u,:a)"),
                {
                    "r": request.form["room"],
                    "c": request.form["cinema"],
                    "k": request.form["kind"],
                    "d": request.form["description"],
                    "u": request.form["urgency"],
                    "a": session["user_id"],
                },
            )
        return redirect(url_for("dashboard"))

    return render_template("edit_issue.html", issue=None)

@app.route("/issue/<int:issue_id>/edit", methods=["GET","POST"])
def edit_issue(issue_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    with engine.begin() as conn:
        issue = conn.execute(text("SELECT * FROM issues WHERE id=:i"), {"i": issue_id}).mappings().first()

        if not issue:
            flash("Problema non trovato", "danger")
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            conn.execute(
                text("UPDATE issues SET room=:r, cinema=:c, kind=:k, description=:d, urgency=:u, status=:s, updated_at=CURRENT_TIMESTAMP WHERE id=:i"),
                {
                    "r": request.form["room"],
                    "c": request.form["cinema"],
                    "k": request.form["kind"],
                    "d": request.form["description"],
                    "u": request.form["urgency"],
                    "s": request.form["status"],
                    "i": issue_id,
                },
            )
            return redirect(url_for("dashboard"))

    return render_template("edit_issue.html", issue=issue)

@app.route("/issue/<int:issue_id>/delete")
def delete_issue(issue_id):
    if "role" not in session or session["role"] != "admin":
        flash("Solo admin può eliminare", "danger")
        return redirect(url_for("dashboard"))

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM issues WHERE id=:i"), {"i": issue_id})

    return redirect(url_for("dashboard"))

# ------------------- ADMIN -------------------

@app.route("/admin/users")
def admin_users():
    if "role" not in session or session["role"] != "admin":
        return redirect(url_for("dashboard"))

    with engine.begin() as conn:
        users = conn.execute(text("SELECT * FROM users ORDER BY created_at DESC")).mappings().all()

    return render_template("admin_users.html", users=users)

@app.route("/admin/users/new", methods=["GET","POST"])
def new_user():
    if "role" not in session or session["role"] != "admin":
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO users(username, password_hash, role) VALUES (:u,:p,:r)"),
                {
                    "u": request.form["username"],
                    "p": generate_password_hash(request.form["password"]),
                    "r": request.form["role"],
                },
            )
        return redirect(url_for("admin_users"))

    return render_template("edit_user.html", user=None)

@app.route("/admin/users/<int:user_id>/edit", methods=["GET","POST"])
def edit_user(user_id):
    if "role" not in session or session["role"] != "admin":
        return redirect(url_for("dashboard"))

    with engine.begin() as conn:
        user = conn.execute(text("SELECT * FROM users WHERE id=:i"), {"i": user_id}).mappings().first()
        if not user:
            flash("Utente non trovato", "danger")
            return redirect(url_for("admin_users"))

        if request.method == "POST":
            updates = {"u": request.form["username"], "r": request.form["role"], "i": user_id}
            sql = "UPDATE users SET username=:u, role=:r"
            if request.form.get("password"):
                sql += ", password_hash=:p"
                updates["p"] = generate_password_hash(request.form["password"])
            sql += " WHERE id=:i"
            conn.execute(text(sql), updates)
            return redirect(url_for("admin_users"))

    return render_template("edit_user.html", user=user)

@app.route("/admin/users/<int:user_id>/delete")
def delete_user(user_id):
    if "role" not in session or session["role"] != "admin":
        return redirect(url_for("dashboard"))

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE id=:i"), {"i": user_id})

    return redirect(url_for("admin_users"))

# ------------------- START -------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
