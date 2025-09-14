# app.py
import os
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, abort
)
from werkzeug.security import check_password_hash, generate_password_hash

from models import db, User, Problem


def create_app():
    app = Flask(__name__)

    # Config base
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///sigra.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["TEMPLATES_AUTO_RELOAD"] = True

    # Init DB
    db.init_app(app)
    with app.app_context():
        db.create_all()

    # ------------------- Helper: decorators -------------------

    def login_required(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            return f(*args, **kwargs)
        return wrapper

    def admin_required(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if session.get("role") != "admin":
                abort(403)
            return f(*args, **kwargs)
        return wrapper

    # ------------------- Auth -------------------

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            user = User.query.filter_by(username=username).first()
            if not user or not check_password_hash(user.password_hash, password):
                flash("Credenziali non valide.", "danger")
                return render_template("login.html")

            # Login ok
            session["user_id"] = user.id
            session["username"] = user.username
            session["role"] = user.role
            flash(f"Benvenuto, {user.username}!", "success")
            return redirect(url_for("dashboard"))

        # GET
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("Disconnesso con successo.", "info")
        return redirect(url_for("login"))

    # ------------------- Dashboard -------------------

    @app.route("/")
    @app.route("/dashboard")
    @login_required
    def dashboard():
        # Mostra tutti i problemi (ordinamento iniziale: id desc)
        problems = Problem.query.order_by(Problem.id.desc()).all()
        return render_template("dashboard.html", problems=problems)

    # ------------------- CRUD Problemi -------------------

    @app.route("/add_problem", methods=["POST"])
    @login_required
    def add_problem():
        """
        Crea un nuovo problema.
        - Legge 'apertura' (datetime-local: 'YYYY-MM-DDTHH:MM')
        - 'cinema' non è più usato in UI -> lo lasciamo vuoto per compatibilità DB
        """
        # Apertura
        apertura_str = request.form.get("apertura")
        try:
            # datetime-local invia stringa senza timezone; la teniamo come naive UTC-like
            apertura = datetime.fromisoformat(apertura_str) if apertura_str else datetime.utcnow()
        except Exception:
            apertura = datetime.utcnow()

        sala = (request.form.get("sala") or "").strip()
        tipo = (request.form.get("tipo") or "").strip()
        urgenza = request.form.get("urgenza") or "Non urgente"

        if not sala or not tipo:
            flash("Compila tutti i campi obbligatori.", "warning")
            return redirect(url_for("dashboard"))

        current_user = User.query.get(session["user_id"])
        autore = current_user.username if current_user else "sconosciuto"

        problem = Problem(
            cinema="",                # campo legacy, lasciato vuoto
            sala=sala,
            tipo=tipo,
            urgenza=urgenza,
            stato="Aperto",
            autore=autore,
            apertura=apertura
        )
        db.session.add(problem)
        db.session.commit()
        flash("Problema registrato con successo!", "success")
        return redirect(url_for("dashboard"))

    @app.route("/edit_problem/<int:problem_id>", methods=["GET", "POST"])
    @login_required
    @admin_required
    def edit_problem(problem_id: int):
        problem = Problem.query.get_or_404(problem_id)

        if request.method == "POST":
            # Consentiamo di aggiornare sala/tipo/urgenza/stato/apertura
            sala = (request.form.get("sala") or "").strip()
            tipo = (request.form.get("tipo") or "").strip()
            urgenza = request.form.get("urgenza") or problem.urgenza
            stato = request.form.get("stato") or problem.stato

            apertura_str = request.form.get("apertura")
            if apertura_str:
                try:
                    problem.apertura = datetime.fromisoformat(apertura_str)
                except Exception:
                    flash("Formato data/ora non valido. Lasciata invariata.", "warning")

            if sala:
                problem.sala = sala
            if tipo:
                problem.tipo = tipo
            problem.urgenza = urgenza
            problem.stato = stato

            db.session.commit()
            flash("Problema aggiornato.", "success")
            return redirect(url_for("dashboard"))

        # GET -> mostra form di modifica (crea un semplice template o riusa uno esistente)
        return render_template("edit_problem.html", problem=problem)

    @app.route("/delete_problem/<int:problem_id>", methods=["POST"])
    @login_required
    @admin_required
    def delete_problem(problem_id: int):
        problem = Problem.query.get_or_404(problem_id)
        db.session.delete(problem)
        db.session.commit()
        flash("Problema eliminato.", "info")
        return redirect(url_for("dashboard"))

    # ------------------- Admin utenti -------------------

    @app.route("/admin/users", endpoint="admin_users", methods=["GET", "POST"])
    @login_required
    @admin_required
    def admin_users():
        """
        Semplice gestione utenti:
        - GET: lista utenti
        - POST: crea utente (username, password, role)
        """
        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            role = (request.form.get("role") or "user").strip().lower()
            if role not in {"user", "admin"}:
                role = "user"

            if not username or not password:
                flash("Username e password sono obbligatori.", "warning")
                return redirect(url_for("admin_users"))

            if User.query.filter_by(username=username).first():
                flash("Username già esistente.", "danger")
                return redirect(url_for("admin_users"))

            user = User(
                username=username,
                password_hash=generate_password_hash(password),
                role=role
            )
            db.session.add(user)
            db.session.commit()
            flash("Utente creato.", "success")
            return redirect(url_for("admin_users"))

        users = User.query.order_by(User.id.asc()).all()
        return render_template("admin_users.html", users=users)

    # ------------------- Utility: crea admin iniziale (opzionale) -------------------

    @app.route("/init-admin")
    def init_admin():
        """
        Crea un utente admin di default se non esiste.
        Usa variabili d'ambiente:
          INIT_ADMIN_USER (default: admin)
          INIT_ADMIN_PASS (default: admin)
        """
        username = os.environ.get("INIT_ADMIN_USER", "admin")
        password = os.environ.get("INIT_ADMIN_PASS", "admin")
        if User.query.filter_by(username=username).first():
            flash("Admin già presente.", "info")
            return redirect(url_for("login"))

        user = User(username=username,
                    password_hash=generate_password_hash(password),
                    role="admin")
        db.session.add(user)
        db.session.commit()
        flash(f"Creato admin '{username}'.", "success")
        return redirect(url_for("login"))

    return app


# Avvio locale
if __name__ == "__main__":
    app = create_app()
    # Host 0.0.0.0 per container/docker; cambia la porta con PORT env se vuoi
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
