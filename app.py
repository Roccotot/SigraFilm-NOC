import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

# usa il tuo models.py
from models import db, User

app = Flask(__name__)

# ---------------------------
# Config DB
# ---------------------------
raw_db_url = os.environ.get("DATABASE_URL", "sqlite:///app.db")
if raw_db_url.startswith("postgres://"):
    raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)
if raw_db_url.startswith("postgresql://") and "render.com" in raw_db_url and "sslmode=" not in raw_db_url:
    sep = "&" if "?" in raw_db_url else "?"
    raw_db_url = f"{raw_db_url}{sep}sslmode=require"

app.config["SQLALCHEMY_DATABASE_URI"] = raw_db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.environ.get("SECRET_KEY", "devsecret")

db.init_app(app)

# ---------------------------
# Routes base
# ---------------------------
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        u = db.session.execute(db.select(User).filter_by(username=username)).scalar()
        if u and check_password_hash(u.password_hash, password):
            session["user_id"] = u.id
            session["role"] = u.role
            flash("Login effettuato", "success")
            return redirect(url_for("dashboard"))

        flash("Credenziali non valide", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logout effettuato", "info")
    return redirect(url_for("login"))

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("dashboard.html")

# ---------------------------
# Gestione utenti
# ---------------------------
def require_admin():
    if session.get("role") != "admin":
        abort(403, description="Accesso negato (solo admin)")

@app.route("/users", methods=["GET", "POST"])
def users():
    require_admin()

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        role = (request.form.get("role") or "user").strip() or "user"

        if not username or len(password) < 8:
            flash("Username obbligatorio e password di almeno 8 caratteri.", "danger")
            return redirect(url_for("users"))

        existing = db.session.execute(db.select(User).filter_by(username=username)).scalar()
        if existing:
            flash("Username già in uso.", "warning")
            return redirect(url_for("users"))

        u = User(username=username, role=role, password_hash=generate_password_hash(password))
        db.session.add(u)
        db.session.commit()
        flash("Utente creato con successo.", "success")
        return redirect(url_for("users"))

    users_list = db.session.execute(db.select(User).order_by(User.id.asc())).scalars().all()
    return render_template("users.html", users=users_list)

@app.route("/users/<int:user_id>/reset", methods=["POST"])
def reset_password(user_id):
    require_admin()
    new_password = (request.form.get("new_password") or "").strip()
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

@app.route("/users/<int:user_id>/delete", methods=["POST"])
def delete_user(user_id):
    require_admin()
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

# ---------------------------
# Debug
# ---------------------------
@app.route("/healthz")
def healthz():
    try:
        total_users = db.session.execute(db.select(db.func.count()).select_from(User)).scalar() or 0
        return jsonify(status="ok", users=total_users)
    except Exception as e:
        return jsonify(status="error", error=str(e)), 500

@app.route("/debug_login")
def debug_login():
    u = db.session.execute(db.select(User).filter_by(username="admin")).scalar()
    if not u:
        return {"found": False}, 404
    return {
        "found": True,
        "username": u.username,
        "hash": u.password_hash,
        "check_Password123!": check_password_hash(u.password_hash, "Password123!"),
    }

# ---------------------------
# Main
# ---------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)
