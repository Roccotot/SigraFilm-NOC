import os
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import check_password_hash, generate_password_hash

from models import db, User, Problem


def create_app():
    app = Flask(__name__)

    # --- Config base ---
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    # Normalizza postgres:// -> postgresql:// per SQLAlchemy
    uri = os.environ.get("DATABASE_URL", "sqlite:///sigra.db")
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = uri

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["TEMPLATES_AUTO_RELOAD"] = True

    # --- DB ---
    db.init_app(app)
    with app.app_context():
        db.create_all()

    # --- Helpers ---
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

    # --- Auth ---
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            user = User.query.filter_by(username=username).first()
            if not user or not check_password_hash(user.password_hash, password):
                flash("Credenziali non valide.", "danger")
                return render_template("login.html")

            session["user_id"] = user.id
            session["username"] = user.username
            session["role"] = user.role
            flash(f"Benvenuto, {user.username}!", "success")
            return redirect(url_for("dashboard"))
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("Disconnesso con successo.", "info")
        return redirect(url_for("login"))

    # --- Dashboard ---
    @app.route("/")
    @app.route("/dashboard")
    @login_required
    def dashboard():
        problems = Problem.query.order_by(Problem.id.desc()).all()
        return render_template("dashboard.html", problems=problems)

    # --- CRUD Problemi ---
    @app.route("/add_problem", methods=["POST"])
    @login_required
    def add_problem():
        # NUOVO: data/ora apertura dal form (datetime-local -> stringa ISO senza timezone)
        apertura_str = request.form.get("apertura")
        try:
            apertura = datetime.fromisoformat(apertura_str) if apertura_str else datetime.utcnow()
        except ValueError:
            apertura = datetime.utcnow()

        sala = (request.form.get("sala") or "").strip()
        tipo = (request.form.get("tipo") or "").strip()
        urgenza = request.form.get("urgenza") or "Non urgente"

        if not sala or not tipo:
            flash("Compila tutti i campi obbligatori.", "warning")
            return redirect(url_for("dashboard"))

        autore = User.query.get(session["user_id"]).username

        new_problem = Problem(
            sala=sala,
            tipo=tipo,
            urgenza=urgenza,
            stato="Aperto",
            autore=autore,
            apertura=apertura
        )
        db.session.add(new_problem)
        db.session.commit()
        flash("Problema registrato con successo!", "success")
        return redirect(url_for("dashboard"))

    @app.route("/edit_problem/<int:problem_id>", methods=["GET", "POST"])
    @login_required
    @admin_required
    def edit_problem(problem_id: int):
        p = Problem.query.get_or_404(problem_id)
        if request.method == "POST":
            p.sala = (request.form.get("sala") or p.sala).strip()
            p.tipo = (request.form.get("tipo") or p.tipo).strip()
            p.urgenza = request.form.get("urgenza") or p.urgenza
            p.stato = request.form.get("stato") or p.stato

            apertura_str = request.form.get("apertura")
            if apertura_str:
                try:
                    p.apertura = datetime.fromisoformat(apertura_str)
                except ValueError:
                    flash("Formato data/ora non valido. Apertura non modificata.", "warning")

            db.session.commit()
            flash("Problema aggiornato.", "success")
            return redirect(url_for("dashboard"))

        return render_template("edit_problem.html", problem=p)

    @app.route("/delete_problem/<int:problem_id>", methods=["POST"])
    @login_required
    @admin_required
    def delete_problem(problem_id: int):
        p = Problem.query.get_or_404(problem_id)
        db.session.delete(p)
        db.session.commit()
        flash("Problema eliminato.", "info")
        return redirect(url_for("dashboard"))

    # --- Admin utenti (se già presente nei tuoi template) ---
    @app.route("/admin/users", endpoint="admin_users", methods=["GET", "POST"])
    @login_required
    @admin_required
    def admin_users():
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

    return app


# Istanza globale per Gunicorn (app:app)
app = create_app()

# Avvio locale
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
