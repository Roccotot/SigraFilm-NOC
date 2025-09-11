import os
import sqlite3
from datetime import datetime
from flask import Flask, g, render_template, request, redirect, url_for, session, flash, abort, Response
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

APP_SECRET = os.environ.get("APP_SECRET", "dev-secret-change-me")

app = Flask(__name__)
app.config.update(
    SECRET_KEY=APP_SECRET,
    DATABASE=os.path.join(app.root_path, 'sigrafilm.db'),
)

# ---------------------- DB helpers ----------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"], detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user','admin')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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
);
"""

def init_db():
    db = get_db()
    db.executescript(SCHEMA_SQL)
    # crea admin se non esiste
    cur = db.execute("SELECT id FROM users WHERE username=?", ("admin",))
    if cur.fetchone() is None:
        db.execute(
            "INSERT INTO users(username, password_hash, role) VALUES (?,?,?)",
            ("admin", generate_password_hash("SigraFilm2025"), "admin"),
        )
        db.commit()

# inizializza subito all’avvio dell’app
with app.app_context():
    init_db()


# ---------------------- Auth utils ----------------------

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    db = get_db()
    row = db.execute("SELECT id, username, role FROM users WHERE id=?", (uid,)).fetchone()
    return row

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user or user["role"] != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped

# ---------------------- Routes ----------------------

@app.get("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            flash("Benvenuto, {}".format(user["username"]))
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Credenziali non valide", "danger")
    return render_template("login.html")

@app.get("/logout")
@login_required
def logout():
    session.clear()
    flash("Sei uscito")
    return redirect(url_for("login"))

@app.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    user = current_user()
    db = get_db()

    if request.method == "POST":
        room = request.form.get("room", "").strip()
        cinema = request.form.get("cinema", "").strip()
        kind = request.form.get("kind", "").strip()
        description = request.form.get("description", "").strip()
        urgency = request.form.get("urgency", "Non urgente").strip()

        if not (room and cinema and kind and description):
            flash("Compila tutti i campi", "danger")
        else:
            db.execute(
                "INSERT INTO issues(room, cinema, kind, description, urgency, author_id) VALUES (?,?,?,?,?,?)",
                (room, cinema, kind, description, urgency, user["id"]),
            )
            db.commit()
            flash("Problema registrato", "success")
            return redirect(url_for("dashboard"))

    if user["role"] == "admin":
        issues = db.execute(
            """
            SELECT i.*, u.username AS author
            FROM issues i JOIN users u ON u.id = i.author_id
            ORDER BY i.created_at DESC LIMIT 50
            """
        ).fetchall()
    else:
        issues = db.execute(
            """
            SELECT i.*, u.username AS author
            FROM issues i JOIN users u ON u.id = i.author_id
            WHERE i.author_id=?
            ORDER BY i.created_at DESC LIMIT 50
            """,
            (user["id"],),
        ).fetchall()

    return render_template("dashboard.html", user=user, issues=issues)

@app.route("/issue/<int:issue_id>/edit", methods=["GET", "POST"])
@login_required
def edit_issue(issue_id):
    db = get_db()
    issue = db.execute("SELECT * FROM issues WHERE id=?", (issue_id,)).fetchone()
    if not issue:
        abort(404)
    user = current_user()
    if user["role"] != "admin" and issue["author_id"] != user["id"]:
        abort(403)

    if request.method == "POST":
        room = request.form.get("room", issue["room"]).strip()
        cinema = request.form.get("cinema", issue["cinema"]).strip()
        kind = request.form.get("kind", issue["kind"]).strip()
        description = request.form.get("description", issue["description"]).strip()
        urgency = request.form.get("urgency", issue["urgency"]).strip()
        status = request.form.get("status", issue["status"]).strip()

        db.execute(
            "UPDATE issues SET room=?, cinema=?, kind=?, description=?, urgency=?, status=?, updated_at=? WHERE id=?",
            (room, cinema, kind, description, urgency, status, datetime.utcnow(), issue_id),
        )
        db.commit()
        flash("Problema aggiornato", "success")
        return redirect(url_for("dashboard"))

    return render_template("edit_issue.html", issue=issue)

@app.post("/issue/<int:issue_id>/delete")
@login_required
def delete_issue(issue_id):
    db = get_db()
    issue = db.execute("SELECT * FROM issues WHERE id=?", (issue_id,)).fetchone()
    if not issue:
        abort(404)
    user = current_user()
    if user["role"] != "admin" and issue["author_id"] != user["id"]:
        abort(403)
    db.execute("DELETE FROM issues WHERE id=?", (issue_id,))
    db.commit()
    flash("Problema eliminato", "info")
    return redirect(url_for("dashboard"))

@app.get("/admin/users")
@admin_required
def admin_users():
    db = get_db()
    users = db.execute("SELECT id, username, role, created_at FROM users ORDER BY created_at DESC").fetchall()
    return render_template("admin_users.html", users=users)

@app.route("/admin/users/create", methods=["POST"])
@admin_required
def admin_users_create():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "user")
    if not username or not password:
        flash("Username e password obbligatori", "danger")
        return redirect(url_for("admin_users"))
    db = get_db()
    try:
        db.execute(
            "INSERT INTO users(username, password_hash, role) VALUES (?,?,?)",
            (username, generate_password_hash(password), role),
        )
        db.commit()
        flash("Utente creato", "success")
    except sqlite3.IntegrityError:
        flash("Username già esistente", "danger")
    return redirect(url_for("admin_users"))

@app.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_users_edit(user_id):
    db = get_db()
    user = db.execute("SELECT id, username, role FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        abort(404)
    if request.method == "POST":
        username = request.form.get("username", user["username"]).strip()
        role = request.form.get("role", user["role"]).strip()
        new_password = request.form.get("password", "").strip()
        if new_password:
            db.execute(
                "UPDATE users SET username=?, role=?, password_hash=? WHERE id=?",
                (username, role, generate_password_hash(new_password), user_id),
            )
        else:
            db.execute(
                "UPDATE users SET username=?, role=? WHERE id=?",
                (username, role, user_id),
            )
        db.commit()
        flash("Utente aggiornato", "success")
        return redirect(url_for("admin_users"))
    return render_template("edit_user.html", item=user)

@app.post("/admin/users/<int:user_id>/delete")
@admin_required
def admin_users_delete(user_id):
    db = get_db()
    me = current_user()
    if me["id"] == user_id:
        flash("Non puoi eliminare il tuo stesso utente", "warning")
        return redirect(url_for("admin_users"))
    db.execute("DELETE FROM users WHERE id=?", (user_id,))
    db.commit()
    flash("Utente eliminato", "info")
    return redirect(url_for("admin_users"))

# ---------------------- Avvio ----------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
