from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, abort, jsonify
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
from sqlalchemy.engine.url import make_url
import os
from sqlalchemy import inspect

# --- CONFIG ---
# --------------------
# CONFIG
# --------------------
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///app.db"
)

db_url = os.environ.get("DATABASE_URL", "sqlite:///app.db")

# ✅ Corregge eventuali URL da Neon/Render
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif db_url.startswith("psql "):  # se incollata stringa "psql '...'"
    db_url = db_url.split("'", 1)[-1].rsplit("'", 1)[0]

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.environ.get("SECRET_KEY", "devsecret")

# 📦 DEBUG: stampa il database usato
print("📦 DATABASE CONNESSO:", app.config["SQLALCHEMY_DATABASE_URI"])
# 📦 Log utile per capire se il DB è connesso
try:
    url_parsed = make_url(app.config["SQLALCHEMY_DATABASE_URI"])
    print(f"📦 DATABASE CONNESSO: {url_parsed.drivername}://{url_parsed.host}/{url_parsed.database}")
except Exception as e:
    print("❌ Errore nel parsing del DATABASE_URL:", e)

db = SQLAlchemy(app)

# --- MODELLI ---
# --------------------
# MODELLI
# --------------------
class User(db.Model):
__tablename__ = "users"

id = db.Column(db.Integer, primary_key=True)
username = db.Column(db.String(80), unique=True, nullable=False)
password_hash = db.Column(db.Text, nullable=False)
@@ -33,7 +51,6 @@ def __repr__(self):

class Problem(db.Model):
__tablename__ = "problems"

id = db.Column(db.Integer, primary_key=True)
cinema = db.Column(db.String(100), nullable=False)
tipo = db.Column(db.Text, nullable=False)
@@ -45,39 +62,66 @@ class Problem(db.Model):
def __repr__(self):
return f"<Problem {self.id} - {self.tipo[:20]}>"

# --------------------
# DECORATORI
# --------------------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("role") != "admin":
            return "Accesso negato", 403
        return f(*args, **kwargs)
    return decorated

# --------------------
# INIT DB (solo 1 volta)
# --------------------
@app.route("/init-db", methods=["POST"])
def init_db():
    """Crea le tabelle e l'utente admin se non esiste.
       Protezione tramite X-Init-Token."""
    token_req = request.headers.get("X-Init-Token", "")
    token_env = os.environ.get("INIT_TOKEN", "")
    if not token_env or token_req != token_env:
        return "Accesso negato", 403

    db.create_all()

    # Crea admin se non esiste
    admin = db.session.execute(db.select(User).filter_by(username="admin")).scalar()
    if not admin:
        default_pwd = os.environ.get("ADMIN_DEFAULT_PASSWORD", "changeme123")
        admin = User(
            username="admin",
            role="admin",
            password_hash=generate_password_hash(default_pwd)
        )
        db.session.add(admin)
        db.session.commit()

    return jsonify({"ok": True, "msg": "Tabelle create e admin pronto."})

# --- BOOTSTRAP DATABASE (crea tabelle + admin se non esistono) ---
def bootstrap_db():
    with app.app_context():
        engine = db.engine
        insp = inspect(engine)

        if not insp.has_table("users"):
            User.__table__.create(bind=engine)
        if not insp.has_table("problems"):
            Problem.__table__.create(bind=engine)

        # Crea utente admin se non esiste
        admin_user = db.session.execute(db.select(User).filter_by(username="admin")).scalar()
        if not admin_user:
            admin = User(
                username="admin",
                role="admin",
                password_hash=generate_password_hash("admin1234")
            )
            db.session.add(admin)
            db.session.commit()
            print("✅ Admin creato automaticamente (admin / admin1234)")

bootstrap_db()

# --- HOME ---
# --------------------
# ROUTES
# --------------------
@app.route("/")
def index():
if "user_id" in session:
return redirect(url_for("dashboard"))
return redirect(url_for("login"))

@app.route("/health")
def health():
    return "ok", 200

# --- LOGIN ---
@app.route("/login", methods=["GET", "POST"])
def login():
@@ -105,37 +149,28 @@ def logout():

# --- DASHBOARD ---
@app.route("/dashboard")
@login_required
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

filter_urgenza = request.args.get("filter_urgenza", "")
filter_stato = request.args.get("filter_stato", "")

query = Problem.query
    if session["role"] != "admin":
        query = query.filter_by(autore=session["username"])
    if session.get("role") != "admin":
        query = query.filter_by(autore=session.get("username"))

if filter_urgenza:
query = query.filter_by(urgenza=filter_urgenza)
if filter_stato:
query = query.filter_by(stato=filter_stato)

problems = query.order_by(Problem.data_ora.desc()).all()

    return render_template(
        "dashboard.html",
        problems=problems,
        filter_urgenza=filter_urgenza,
        filter_stato=filter_stato
    )
    return render_template("dashboard.html", problems=problems,
                           filter_urgenza=filter_urgenza, filter_stato=filter_stato)

# --- AGGIUNGI PROBLEMA ---
@app.route("/problems/add", methods=["POST"])
@login_required
def add_problem():
    if "user_id" not in session:
        return redirect(url_for("login"))

cinema = request.form.get("cinema", "").strip()
tipo = request.form.get("tipo", "").strip()
urgenza = request.form.get("urgenza", "Non urgente")
@@ -159,15 +194,13 @@ def add_problem():

# --- MODIFICA PROBLEMA ---
@app.route("/problems/<int:problem_id>/edit", methods=["GET", "POST"])
@login_required
def edit_problem(problem_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

p = db.session.get(Problem, problem_id)
if not p:
abort(404)

    if session["role"] != "admin" and session["username"] != p.autore:
    if session.get("role") != "admin" and session.get("username") != p.autore:
return "Accesso negato", 403

if request.method == "POST":
@@ -183,15 +216,13 @@ def edit_problem(problem_id):

# --- ELIMINA PROBLEMA ---
@app.route("/problems/<int:problem_id>/delete", methods=["POST"])
@login_required
def delete_problem(problem_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

p = db.session.get(Problem, problem_id)
if not p:
abort(404)

    if session["role"] != "admin" and session["username"] != p.autore:
    if session.get("role") != "admin" and session.get("username") != p.autore:
return "Accesso negato", 403

db.session.delete(p)
@@ -201,10 +232,8 @@ def delete_problem(problem_id):

# --- GESTIONE UTENTI ---
@app.route("/users", methods=["GET", "POST"])
@admin_required
def admin_users():
    if session.get("role") != "admin":
        return "Accesso negato", 403

if request.method == "POST":
username = request.form.get("username", "").strip()
password = request.form.get("password", "")
@@ -230,10 +259,8 @@ def admin_users():

# --- RESET PASSWORD ---
@app.route("/users/<int:user_id>/reset", methods=["POST"])
@admin_required
def reset_password(user_id):
    if session.get("role") != "admin":
        return "Accesso negato", 403

new_password = request.form.get("new_password", "").strip()
if len(new_password) < 8:
flash("La nuova password deve avere almeno 8 caratteri.", "danger")
@@ -250,10 +277,8 @@ def reset_password(user_id):

# --- ELIMINA UTENTE ---
@app.route("/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def delete_user(user_id):
    if session.get("role") != "admin":
        return "Accesso negato", 403

if session.get("user_id") == user_id:
flash("Non puoi eliminare il tuo stesso utente mentre sei loggato.", "warning")
return redirect(url_for("admin_users"))
@@ -268,11 +293,8 @@ def delete_user(user_id):
flash(f"Utente '{username}' eliminato.", "success")
return redirect(url_for("admin_users"))

# --- HEALTHCHECK ---
@app.route("/healthz")
def healthz():
    return "ok", 200

# --- MAIN ---
# --------------------
# MAIN
# --------------------
if __name__ == "__main__":
app.run(host="0.0.0.0", port=5000, debug=True)
