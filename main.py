import os
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, abort, Response, g
)
from werkzeug.security import generate_password_hash, check_password_hash

# --- SQLAlchemy (DB-agnostico: Postgres in prod, SQLite in locale) ---
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

APP_SECRET = os.environ.get("APP_SECRET", "dev-secret-change-me")

# DATABASE_URL: impostata da Render quando colleghi il Postgres
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///sigrafilm.db")

# Normalizza "postgres://" -> "postgresql+psycopg2://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    # driver default: psycopg2
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)

app = Flask(__name__)
app.config["SECRET_KEY"] = APP_SECRET

# ---------------------- DB session helpers ----------------------
def get_db():
    """
    Ritorna una connessione SQLAlchemy (Connection) legata alla richiesta.
    Usa transazioni esplicite solo dove necessario (INSERT/UPDATE/DELETE).
    """
    if "db_conn" not in g:
        g.db_conn = engine.connect()
    return g.db_conn

@app.teardown_appcontext
def close_db(error=None):
    conn = g.pop("db_conn", None)
    if conn is not None:
        conn.close()

# ---------------------- Schema creation ----------------------
SCHEMA_SQL_SQLITE = """
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
    with engine.begin() as conn:  # transaction
        dialect = engine.url.get_backend_name()
        if dialect == "sqlite":
            conn.exec_driver_sql(SCHEMA_SQL_SQLITE)
        else:
            conn.exec_driver_sql(SCHEMA_SQL_POSTGRES)

        # crea admin se non esiste
        exists = conn.execute(
            text("SELECT 1 FROM users WHERE username=:u LIMIT 1"),
            {"u": "admin"},
        ).first()
        if not exists:
            conn.execute(
                text("""
                    INSERT INTO users(username, password_hash, role)
                    VALUES (:u, :p, 'admin')
                """),
                {"u": "admin", "p": generate_password_hash("SigraFilm2025")},
            )

# Inizializza DB all'avvio (Flask 3: niente before_first_request)
with app.app_context():
    init_db()

# ---------------------- Auth utils ----------------------
def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    conn = get_db()
    row = conn.execute(
        text("SELECT id, username, role FROM users WHERE id=:id"),
        {"id": uid},
    ).mappings().first()
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

# ---------------------- Query helper per filtri ----------------------
def build_issue_query(user, args, limit=200):
    where = []
    params = {}

    # visibilità: utente normale vede solo i propri
    if user["role"] != "admin":
        where.append("i.author_id = :author_id")
        params["author_id"] = user["id"]

    # filtri
    cinema = args.get("cinema", "").strip()
    status = args.get("status", "").strip()
    q = args.get("q", "").strip()
    if cinema:
        where.append("i.cinema LIKE :cinema")
        params["cinema"] = f"%{cinema}%"
    if status:
        where.append("i.status = :status")
        params["status"] = status
    if q:
        where.append("(i.description LIKE :q OR i.kind LIKE :q OR i.room LIKE :q OR i.cinema LIKE :q)")
        params["q"] = f"%{q}%"

    sql = (
        "SELECT i.*, u.username AS author FROM issues i "
        "JOIN users u ON u.id = i.author_id "
    )
    if where:
        sql += "WHERE " + " AND ".join(where) + " "
    sql += "ORDER BY i.created_at DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"

    return sql, params, {"cinema": cinema, "status": status, "q": q}

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
        conn = get_db()
        user = conn.execute(
            text("SELECT * FROM users WHERE username=:u"),
            {"u": username},
        ).mappings().first()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            flash(f"Benvenuto, {user['username']}")
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
    conn = get_db()

    if request.method == "POST":
        room = request.form.get("room", "").strip()
        cinema = request.form.get("cinema", "").strip()
        kind = request.form.get("kind", "").strip()
        description = request.form.get("description", "").strip()
        urgency = request.form.get("urgency", "Non urgente").strip()

        if not (room and cinema and kind and description):
            flash("Compila tutti i campi", "danger")
        else:
            with conn.begin():
                conn.execute(
                    text("""
                        INSERT INTO issues(room, cinema, kind, description, urgency, author_id)
                        VALUES (:room, :cinema, :kind, :description, :urgency, :author_id)
                    """),
                    {
                        "room": room,
                        "cinema": cinema,
                        "kind": kind,
                        "description": description,
                        "urgency": urgency,
                        "author_id": user["id"],
                    },
                )
            flash("Problema registrato", "success")
            return redirect(url_for("dashboard"))

    sql, params, filters = build_issue_query(user, request.args, limit=200)
    issues = conn.execute(text(sql), params).mappings().all()

    export_url = url_for('export_csv', **{k: v for k, v in filters.items() if v})
    return render_template("dashboard.html", user=user, issues=issues, filters=filters, export_url=export_url)

@app.route("/issue/<int:issue_id>/edit", methods=["GET", "POST"])
@login_required
def edit_issue(issue_id):
    conn = get_db()
    issue = conn.execute(
        text("SELECT * FROM issues WHERE id=:id"),
        {"id": issue_id},
    ).mappings().first()
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

        with conn.begin():
            conn.execute(
                text("""
                    UPDATE issues
                    SET room=:room, cinema=:cinema, kind=:kind, description=:description,
                        urgency=:urgency, status=:status, updated_at=:updated_at
                    WHERE id=:id
                """),
                {
                    "room": room, "cinema": cinema, "kind": kind, "description": description,
                    "urgency": urgency, "status": status, "updated_at": datetime.utcnow(),
                    "id": issue_id,
                },
            )
        flash("Problema aggiornato", "success")
        return redirect(url_for("dashboard"))

    return render_template("edit_issue.html", issue=issue)

@app.post("/issue/<int:issue_id>/delete")
@login_required
def delete_issue(issue_id):
    conn = get_db()
    issue = conn.execute(
        text("SELECT author_id FROM issues WHERE id=:id"),
        {"id": issue_id},
    ).mappings().first()
    if not issue:
        abort(404)
    user = current_user()
    if user["role"] != "admin" and issue["author_id"] != user["id"]:
        abort(403)

    with conn.begin():
        conn.execute(text("DELETE FROM issues WHERE id=:id"), {"id": issue_id})
    flash("Problema eliminato", "info")
    return redirect(url_for("dashboard"))

# ---------------------- Export CSV ----------------------
@app.get('/export.csv')
@login_required
def export_csv():
    import csv, io
    user = current_user()
    conn = get_db()
    sql, params, _filters = build_issue_query(user, request.args, limit=None)
    rows = conn.execute(text(sql), params).mappings().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ID","Sala","Cinema","Tipo","Descrizione","Urgenza","Stato","Autore","Creato","Aggiornato"])
    for r in rows:
        writer.writerow([
            r["id"], r["room"], r["cinema"], r["kind"], r["description"], r["urgency"], r["status"],
            r["author"], r["created_at"], r["updated_at"] or ''
        ])
    csv_data = buf.getvalue()
    fname = f"issues-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"
    return Response(csv_data, mimetype='text/csv', headers={"Content-Disposition": f"attachment; filename={fname}"})

# ---------------------- Admin utenti ----------------------
@app.get("/admin/users")
@admin_required
def admin_users():
    conn = get_db()
    users = conn.execute(
        text("SELECT id, username, role, created_at FROM users ORDER BY created_at DESC")
    ).mappings().all()
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

    conn = get_db()
    try:
        with conn.begin():
            conn.execute(
                text("""
                    INSERT INTO users(username, password_hash, role)
                    VALUES (:u, :p, :r)
                """),
                {"u": username, "p": generate_password_hash(password), "r": role},
            )
        flash("Utente creato", "success")
    except IntegrityError:
        flash("Username già esistente", "danger")
    return redirect(url_for("admin_users"))

@app.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_users_edit(user_id):
    conn = get_db()
    item = conn.execute(
        text("SELECT id, username, role FROM users WHERE id=:id"),
        {"id": user_id},
    ).mappings().first()
    if not item:
        flash(f"Utente con id {user_id} non trovato", "warning")
        return redirect(url_for("admin_users"))

    if request.method == "POST":
        username = request.form.get("username", item["username"]).strip()
        role = request.form.get("role", item["role"]).strip()
        new_password = request.form.get("password", "").strip()
        try:
            with conn.begin():
                if new_password:
                    conn.execute(
                        text("""
                            UPDATE users
                            SET username=:u, role=:r, password_hash=:p
                            WHERE id=:id
                        """),
                        {"u": username, "r": role, "p": generate_password_hash(new_password), "id": user_id},
                    )
                else:
                    conn.execute(
                        text("""
                            UPDATE users
                            SET username=:u, role=:r
                            WHERE id=:id
                        """),
                        {"u": username, "r": role, "id": user_id},
                    )
            flash("Utente aggiornato", "success")
        except IntegrityError:
            flash("Username già esistente", "danger")
        return redirect(url_for("admin_users"))

    return render_template("edit_user.html", item=item)

@app.post("/admin/users/<int:user_id>/delete")
@admin_required
def admin_users_delete(user_id):
    conn = get_db()
    me = current_user()
    if me["id"] == user_id:
        flash("Non puoi eliminare il tuo stesso utente mentre sei loggato", "warning")
        return redirect(url_for("admin_users"))
    with conn.begin():
        conn.execute(text("DELETE FROM users WHERE id=:id"), {"id": user_id})
    flash("Utente eliminato", "info")
    return redirect(url_for("admin_users"))

# ---------------------- Avvio ----------------------
if __name__ == "__main__":
    # In locale: se non hai DATABASE_URL, userai SQLite (sigrafilm.db)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
