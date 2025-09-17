from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

# --- CONFIG ---
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///app.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.environ.get("SECRET_KEY", "devsecret")

db = SQLAlchemy(app)

# --- MODELS ---
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    role = db.Column(db.String(20), default="user")

class Problem(db.Model):
    __tablename__ = "problems"

    id = db.Column(db.Integer, primary_key=True)
    cinema = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.Text, nullable=False)
    urgenza = db.Column(db.String(50), nullable=False)
    stato = db.Column(db.String(50), default="Aperto")
    autore = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# --- HOME ---
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

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
@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        cinema = request.form.get("cinema", "").strip()
        tipo = request.form.get("tipo", "").strip()
        urgenza = request.form.get("urgenza", "Non urgente")

        if not cinema or not tipo:
            flash("Compila tutti i campi.", "danger")
            return redirect(url_for("dashboard"))

        autore = User.query.get(session["user_id"]).username
        p = Problem(cinema=cinema, tipo=tipo, urgenza=urgenza, autore=autore)
        db.session.add(p)
        db.session.commit()
        flash("Problema aggiunto con successo.", "success")
        return redirect(url_for("dashboard"))

    # 👇 Admin vede tutti i problemi, user solo i propri
    if session.get("role") == "admin":
        problems = Problem.query.order_by(Problem.created_at.desc()).all()
    else:
        autore = User.query.get(session["user_id"]).username
        problems = Problem.query.filter_by(autore=autore).order_by(Problem.created_at.desc()).all()

    return render_template("dashboard.html", problems=problems)

# --- MODIFICA PROBLEMA ---
@app.route("/problems/<int:problem_id>/edit", methods=["GET", "POST"])
def edit_problem(problem_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    p = Problem.query.get_or_404(problem_id)

    # 👇 Solo autore o admin possono modificare
    if session.get("role") != "admin" and p.autore != User.query.get(session["user_id"]).username:
        abort(403)

    if request.method == "POST":
        p.cinema = request.form.get("cinema", p.cinema).strip()
        p.tipo = request.form.get("tipo", p.tipo).strip()
        p.urgenza = request.form.get("urgenza", p.urgenza)
        p.stato = request.form.get("stato", p.stato)
        db.session.commit()
        flash("Problema aggiornato con successo.", "success")
        return redirect(url_for("dashboard"))

    return render_template("edit_problem.html", problem=p)

# --- ELIMINA PROBLEMA ---
@app.route("/problems/<int:problem_id>/delete", methods=["POST"])
def delete_problem(problem_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    p = Problem.query.get_or_404(problem_id)

    # 👇 Solo autore o admin possono eliminare
    if session.get("role") != "admin" and p.autore != User.query.get(session["user_id"]).username:
        abort(403)

    db.session.delete(p)
    db.session.commit()
    flash("Problema eliminato.", "success")
    return redirect(url_for("dashboard"))

# --- UTENTI ---
@app.route("/users", methods=["GET", "POST"])
def users():
    if session.get("role") != "admin":
        return "Accesso negato", 403

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "user")

        if not username or len(password) < 8:
            flash("Username obbligatorio e password di almeno 8 caratteri.", "danger")
            return redirect(url_for("users"))

        existing = db.session.execute(db.select(User).filter_by(username=username)).scalar()
        if existing:
            flash("Username già in uso.", "warning")
            return redirect(url_for("users"))

        u = User(username=username, role=role,
                 password_hash=generate_password_hash(password))
        db.session.add(u)
        db.session.commit()
        flash("Utente creato con successo.", "success")
        return redirect(url_for("users"))

    users_list = db.session.execute(
        db.select(User).order_by(User.id.asc())
    ).scalars().all()
    return render_template("users.html", users=users_list)

# --- RESET PASSWORD ---
@app.route("/users/<int:user_id>/reset", methods=["POST"])
def reset_password(user_id):
    if session.get("role") != "admin":
        return "Accesso negato", 403

    new_password = request.form.get("new_password", "").strip()
    if len(new_password) < 8:
        flash("La nuova password deve avere almeno 8 caratteri.", "danger")
        return redirect(url_for("users"))

    u = db.session.get(User, user_id)
    if not u:
        abort(404)

    u.password_hash = generate_password_hash(new_password)
    db.session.commit()
    flash(f"Password di '{u.username}' aggiornata con successo.", "success")
    return redirect(url_for("users"))

# --- ELIMINA UTENTE ---
@app.route("/users/<int:user_id>/delete", methods=["POST"])
def delete_user(user_id):
    if session.get("role") != "admin":
        return "Accesso negato", 403

    if session.get("user_id") == user_id:
        flash("Non puoi eliminare il tuo stesso utente mentre sei loggato.", "warning")
        return redirect(url_for("users"))

    u = db.session.get(User, user_id)
    if not u:
        abort(404)

    username = u.username
    db.session.delete(u)
    db.session.commit()
    flash(f"Utente '{username}' eliminato.", "success")
    return redirect(url_for("users"))

# --- MAIN ---
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)
