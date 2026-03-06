from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

# --- CONFIGURAZIONE ---
app = Flask(__name__)
_db_url = os.environ.get("DATABASE_URL", "sqlite:///app.db")
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = _db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.environ.get("SECRET_KEY", "devsecret")

# DEBUG: stampa database usato
print("📦 DATABASE CONNESSO:", app.config["SQLALCHEMY_DATABASE_URI"])

db = SQLAlchemy(app)

# --- MODELLI ---
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
    comments = db.relationship("Comment", backref="problem", cascade="all, delete-orphan", lazy=True)

    def __repr__(self):
        return f"<Problem {self.id} - {self.tipo[:20]}>"

class Comment(db.Model):
    __tablename__ = "comments"
    id = db.Column(db.Integer, primary_key=True)
    problem_id = db.Column(db.Integer, db.ForeignKey("problems.id", ondelete="CASCADE"), nullable=False)
    autore = db.Column(db.String(80), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user")
    testo = db.Column(db.Text, nullable=False)
    data_ora = db.Column(db.DateTime, default=datetime.utcnow)

class Cinema(db.Model):
    __tablename__ = "cinemas"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True, nullable=False)

    def __repr__(self):
        return f"<Cinema {self.nome}>"

# --- CREAZIONE AUTOMATICA TABELLE + ADMIN ---
with app.app_context():
    db.create_all()
    admin = db.session.execute(db.select(User).filter_by(username="admin")).scalar()
    if not admin:
        admin = User(username="admin", password_hash=generate_password_hash("admin1234"), role="admin")
        db.session.add(admin)
        db.session.commit()
        print("✅ Utente admin creato automaticamente (username: admin / password: admin1234)")
    # Migra cinema già presenti nei problemi
    existing_names = {c.nome for c in Cinema.query.all()}
    for p in Problem.query.all():
        if p.cinema and p.cinema.strip() and p.cinema.strip() not in existing_names:
            db.session.add(Cinema(nome=p.cinema.strip()))
            existing_names.add(p.cinema.strip())
    db.session.commit()

# --- ROUTES ---
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
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    filter_urgenza = request.args.get("filter_urgenza", "")
    filter_stato = request.args.get("filter_stato", "")

    query = Problem.query.filter(Problem.stato != "Chiuso")
    if session["role"] != "admin":
        query = query.filter_by(autore=session["username"])
    if filter_urgenza:
        query = query.filter_by(urgenza=filter_urgenza)
    if filter_stato:
        query = query.filter_by(stato=filter_stato)

    problems = query.order_by(Problem.data_ora.desc()).all()

    # Stats e cinemas dalla lista non filtrata (scope utente, escluso chiusi)
    base_query = Problem.query.filter(Problem.stato != "Chiuso")
    if session["role"] != "admin":
        base_query = base_query.filter_by(autore=session["username"])
    all_problems = base_query.all()

    stats = {
        "total":    len(all_problems),
        "aperto":   sum(1 for p in all_problems if p.stato == "Aperto"),
        "in_corso": sum(1 for p in all_problems if p.stato == "In corso"),
        "chiuso":   0,
        "critico":  sum(1 for p in all_problems if p.urgenza == "Critico"),
    }
    cinemas = Cinema.query.order_by(Cinema.nome.asc()).all()

    return render_template(
        "dashboard.html",
        problems=problems,
        filter_urgenza=filter_urgenza,
        filter_stato=filter_stato,
        stats=stats,
        cinemas=cinemas,
    )

# --- DETTAGLIO TICKET ---
@app.route("/problems/<int:problem_id>", methods=["GET"])
def ticket_detail(problem_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    p = db.session.get(Problem, problem_id)
    if not p:
        abort(404)
    if session["role"] != "admin" and session["username"] != p.autore:
        return "Accesso negato", 403
    comments = Comment.query.filter_by(problem_id=p.id).order_by(Comment.data_ora.asc()).all()
    return render_template("ticket_detail.html", problem=p, comments=comments)

# --- AGGIUNGI COMMENTO ---
@app.route("/problems/<int:problem_id>/comment", methods=["POST"])
def add_comment(problem_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    p = db.session.get(Problem, problem_id)
    if not p:
        abort(404)
    if session["role"] != "admin" and session["username"] != p.autore:
        return "Accesso negato", 403
    testo = request.form.get("testo", "").strip()
    if testo:
        c = Comment(
            problem_id=p.id,
            autore=session["username"],
            role=session["role"],
            testo=testo,
        )
        db.session.add(c)
        db.session.commit()
    return redirect(url_for("ticket_detail", problem_id=p.id) + "#chat-bottom")

# --- AGGIORNA TICKET (stato/urgenza) ---
@app.route("/problems/<int:problem_id>/update", methods=["POST"])
def update_ticket(problem_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    p = db.session.get(Problem, problem_id)
    if not p:
        abort(404)
    if session["role"] != "admin" and session["username"] != p.autore:
        return "Accesso negato", 403
    nuovo_stato   = request.form.get("stato", p.stato)
    nuova_urgenza = request.form.get("urgenza", p.urgenza)
    p.stato   = nuovo_stato
    p.urgenza = nuova_urgenza
    db.session.commit()
    flash("Ticket aggiornato.", "success")
    if nuovo_stato == "Chiuso":
        return redirect(url_for("closed_tickets"))
    return redirect(url_for("ticket_detail", problem_id=p.id))

# --- ARCHIVIO TICKET CHIUSI ---
@app.route("/closed")
def closed_tickets():
    if "user_id" not in session:
        return redirect(url_for("login"))
    query = Problem.query.filter_by(stato="Chiuso")
    if session["role"] != "admin":
        query = query.filter_by(autore=session["username"])
    problems = query.order_by(Problem.data_ora.desc()).all()
    return render_template("closed_tickets.html", problems=problems)

# --- AGGIUNGI PROBLEMA ---
@app.route("/problems/add", methods=["POST"])
def add_problem():
    if "user_id" not in session:
        return redirect(url_for("login"))

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
def edit_problem(problem_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    p = db.session.get(Problem, problem_id)
    if not p:
        abort(404)

    if session["role"] != "admin" and session["username"] != p.autore:
        return "Accesso negato", 403

    if request.method == "POST":
        p.cinema = request.form.get("cinema", p.cinema)
        p.tipo = request.form.get("tipo", p.tipo)
        p.urgenza = request.form.get("urgenza", p.urgenza)
        p.stato = request.form.get("stato", p.stato)
        db.session.commit()
        flash("Problema aggiornato con successo.", "success")
        return redirect(url_for("dashboard"))

    cinemas = Cinema.query.order_by(Cinema.nome.asc()).all()
    return render_template("edit_problem.html", problem=p, cinemas=cinemas)

# --- ELIMINA PROBLEMA ---
@app.route("/problems/<int:problem_id>/delete", methods=["POST"])
def delete_problem(problem_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    p = db.session.get(Problem, problem_id)
    if not p:
        abort(404)

    if session["role"] != "admin" and session["username"] != p.autore:
        return "Accesso negato", 403

    db.session.delete(p)
    db.session.commit()
    flash("Problema eliminato.", "success")
    return redirect(url_for("dashboard"))

# --- GESTIONE UTENTI ---
@app.route("/users", methods=["GET", "POST"])
def admin_users():
    if session.get("role") != "admin":
        return "Accesso negato", 403

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "user")

        if not username or len(password) < 8:
            flash("Username obbligatorio e password di almeno 8 caratteri.", "danger")
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
def reset_password(user_id):
    if session.get("role") != "admin":
        return "Accesso negato", 403

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
def delete_user(user_id):
    if session.get("role") != "admin":
        return "Accesso negato", 403

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

# --- GESTIONE CINEMA (admin) ---
@app.route("/admin/cinemas", methods=["GET", "POST"])
def admin_cinemas():
    if session.get("role") != "admin":
        return "Accesso negato", 403
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        if nome:
            existing = Cinema.query.filter_by(nome=nome).first()
            if existing:
                flash(f"Cinema '{nome}' già presente.", "warning")
            else:
                db.session.add(Cinema(nome=nome))
                db.session.commit()
                flash(f"Cinema '{nome}' aggiunto.", "success")
        return redirect(url_for("admin_cinemas"))
    cinemas = Cinema.query.order_by(Cinema.nome.asc()).all()
    return render_template("cinemas.html", cinemas=cinemas)

@app.route("/admin/cinemas/<int:cinema_id>/edit", methods=["POST"])
def edit_cinema(cinema_id):
    if session.get("role") != "admin":
        return "Accesso negato", 403
    c = db.session.get(Cinema, cinema_id)
    if not c:
        abort(404)
    nuovo_nome = request.form.get("nome", "").strip()
    if nuovo_nome and nuovo_nome != c.nome:
        existing = Cinema.query.filter_by(nome=nuovo_nome).first()
        if existing:
            flash(f"'{nuovo_nome}' esiste già.", "warning")
        else:
            c.nome = nuovo_nome
            db.session.commit()
            flash(f"Cinema rinominato in '{nuovo_nome}'.", "success")
    return redirect(url_for("admin_cinemas"))

@app.route("/admin/cinemas/<int:cinema_id>/delete", methods=["POST"])
def delete_cinema(cinema_id):
    if session.get("role") != "admin":
        return "Accesso negato", 403
    c = db.session.get(Cinema, cinema_id)
    if c:
        nome = c.nome
        db.session.delete(c)
        db.session.commit()
        flash(f"Cinema '{nome}' eliminato.", "success")
    return redirect(url_for("admin_cinemas"))

# --- MAIN ---
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)
