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

# --------------------
# CONFIG
# --------------------
app = Flask(__name__)

db_url = os.environ.get("DATABASE_URL", "sqlite:///app.db")

# ✅ Corregge eventuali URL da Neon/Render
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif db_url.startswith("psql "):  # se incollata stringa "psql '...'"
    db_url = db_url.split("'", 1)[-1].rsplit("'", 1)[0]

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.environ.get("SECRET_KEY", "devsecret")

# 📦 Log utile per capire se il DB è connesso
try:
    url_parsed = make_url(app.config["SQLALCHEMY_DATABASE_URI"])
    print(f"📦 DATABASE CONNESSO: {url_parsed.drivername}://{url_parsed.host}/{url_parsed.database}")
except Exception as e:
    print("❌ Errore nel parsing del DATABASE_URL:", e)

db = SQLAlchemy(app)

# --------------------
# MODELLI
# --------------------
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    role = db.Column(db.String(20), default="user")

    def __repr__(self):
        return f"<User {self.username}>"


class Problem(db.Model):
    __tablename__ = "problems"
    id = db.Column(db.Integer, primary_key=True)
    cinema = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.Text, nullable=False)
    urgenza = db.Column(db.String(50), nullable=False)
    stato = db.Column(db.String(50), default="Aperto")
    autore = db.Column(db.String(80), nullable=False)
    data_ora = db.Column(db.DateTime, default=datetime.utcnow)

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
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        u = db.session.execute(db.select(User).filter_by(username=username)).scalar()
        if u and check_password_hash(u.password_hash, password):
            session["user_id"] = u.id
            session["role"] = u.role
            session["username"] = u.username
            flash("Login effettuato", "success")
            return redirect(url_for("dashboard"))

        flash("Credenziali non valide", "danger")
    return render_template("login.html")

# --- LOGOUT ---
@app.route("/logout")
def logout():
    session.clear()
    flash("Logout effettuato", "info")
    return redirect(url_for("login"))

# --- DASHBOARD ---
@app.route("/dashboard")
@login_required
def dashboard():
    filter_urgenza = request.args.get("filter_urgenza", "")
    filter_stato = request.args.get("filter_stato", "")

    query = Problem.query
    if session.get("role") != "admin":
        query = query.filter_by(autore=session.get("username"))

    if filter_urgenza:
        query = query.filter_by(urgenza=filter_urgenza)
    if filter_stato:
        query = query.filter_by(stato=filter_stato)

    problems = query.order_by(Problem.data_ora.desc()).all()
    return render_template("dashboard.html", problems=problems,
                           filter_urgenza=filter_urgenza, filter_stato=filter_stato)

# --- AGGIUNGI PROBLEMA ---
@app.route("/problems/add", methods=["POST"])
@login_required
def add_problem():
    cinema = request.form.get("cinema", "").strip()
    tipo = request.form.get("tipo", "").strip()
    urgenza = request.form.get("urgenza", "Non urgente")
    stato = request.form.get("stato", "Aperto")

    if not cinema or not tipo:
        flash("Compila tutti i campi.", "danger")
        return redirect(url_for("dashboard"))

    p = Problem(
        cinema=cinema,
        tipo=tipo,
        urgenza=urgenza,
        stato=stato,
        autore=session["username"],
    )
    db.session.add(p)
    db.session.commit()
    flash("Problema aggiunto con successo.", "success")
    return redirect(url_for("dashboard"))

# --- MODIFICA PROBLEMA ---
@app.route("/problems/<int:problem_id>/edit", methods=["GET", "POST"])
@login_required
def edit_problem(problem_id):
    p = db.session.get(Problem, problem_id)
    if not p:
        abort(404)

    if session.get("role") != "admin" and session.get("username") != p.autore:
        return "Accesso negato", 403

    if request.method == "POST":
        p.cinema = request.form.get("cinema", p.cinema)
        p.tipo = request.form.get("tipo", p.tipo)
        p.urgenza = request.form.get("urgenza", p.urgenza)
        p.stato = request.form.get("stato", p.stato)
        db.session.commit()
        flash("Problema aggiornato con successo.", "success")
        return redirect(url_for("dashboard"))

    return render_template("edit_problem.html", problem=p)

# --- ELIMINA PROBLEMA ---
@app.route("/problems/<int:problem_id>/delete", methods=["POST"])
@login_required
def delete_problem(problem_id):
    p = db.session.get(Problem, problem_id)
    if not p:
        abort(404)

    if session.get("role") != "admin" and session.get("username") != p.autore:
        return "Accesso negato", 403

    db.session.delete(p)
    db.session.commit()
    flash("Problema eliminato.", "success")
    return redirect(url_for("dashboard"))

# --- GESTIONE UTENTI ---
@app.route("/users", methods=["GET", "POST"])
@admin_required
def admin_users():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "user")

if not username or not password:
    flash("Username e password sono obbligatori.", "danger")
    return redirect(url_for("admin_users"))


        existing = db.session.execute(db.select(User).filter_by(username=username)).scalar()
        if existing:
            flash("Username già in uso.", "warning")
            return redirect(url_for("admin_users"))

        u = User(username=username, role=role, password_hash=generate_password_hash(password))
        db.session.add(u)
        db.session.commit()
        flash("Utente creato con successo.", "success")
        return redirect(url_for("admin_users"))

    users_list = db.session.execute(db.select(User).order_by(User.id.asc())).scalars().all()
    return render_template("users.html", users=users_list)

# --- RESET PASSWORD ---
@app.route("/users/<int:user_id>/reset", methods=["POST"])
@admin_required
def reset_password(user_id):
    new_password = request.form.get("new_password", "").strip()
    if len(new_password) < 8:
        flash("La nuova password deve avere almeno 8 caratteri.", "danger")
        return redirect(url_for("admin_users"))

    u = db.session.get(User, user_id)
    if not u:
        abort(404)

    u.password_hash = generate_password_hash(new_password)
    db.session.commit()
    flash(f"Password di '{u.username}' aggiornata con successo.", "success")
    return redirect(url_for("admin_users"))

# --- ELIMINA UTENTE ---
@app.route("/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def delete_user(user_id):
    if session.get("user_id") == user_id:
        flash("Non puoi eliminare il tuo stesso utente mentre sei loggato.", "warning")
        return redirect(url_for("admin_users"))

    u = db.session.get(User, user_id)
    if not u:
        abort(404)

    username = u.username
    db.session.delete(u)
    db.session.commit()
    flash(f"Utente '{username}' eliminato.", "success")
    return redirect(url_for("admin_users"))

# --------------------
# MAIN
# --------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
