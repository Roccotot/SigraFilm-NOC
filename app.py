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
    password_plain = db.Column(db.String(200), default="")
    role = db.Column(db.String(20), default="user")
    telefono = db.Column(db.String(30), default="")
    email = db.Column(db.String(120), default="")

    def __repr__(self):
        return f"<User {self.username}>"

class Problem(db.Model):
    __tablename__ = "problems"
    id = db.Column(db.Integer, primary_key=True)
    cinema = db.Column(db.String(100), nullable=False)
    città = db.Column(db.String(100), nullable=False, default="")
    sala = db.Column(db.String(20), nullable=False, default="1")
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
    nome = db.Column(db.String(100), nullable=False)
    città = db.Column(db.String(100), nullable=False, default="")
    num_sale = db.Column(db.Integer, nullable=False, default=1)
    telefono = db.Column(db.String(50), default="")
    indirizzo = db.Column(db.String(200), default="")
    lat = db.Column(db.Float, nullable=True)
    lng = db.Column(db.Float, nullable=True)

    def __repr__(self):
        return f"<Cinema {self.nome} ({self.città})>"

class TicketRead(db.Model):
    __tablename__ = "ticket_reads"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    problem_id = db.Column(db.Integer, nullable=False)
    last_read_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("user_id", "problem_id", name="uq_user_problem"),)

# --- CREAZIONE AUTOMATICA TABELLE + MIGRAZIONI ---
with app.app_context():
    db.create_all()

    # Migrazione colonne mancanti (ALTER TABLE sicuro)
    _migrations = [
        ("problems", "città",    "VARCHAR(100) NOT NULL DEFAULT ''"),
        ("problems", "sala",     "VARCHAR(20)  NOT NULL DEFAULT '1'"),
        ("cinemas",  "città",    "VARCHAR(100) NOT NULL DEFAULT ''"),
        ("cinemas",  "num_sale", "INTEGER      NOT NULL DEFAULT 1"),
        ("cinemas",  "telefono", "VARCHAR(50)  NOT NULL DEFAULT ''"),
        ("cinemas",  "indirizzo","VARCHAR(200) NOT NULL DEFAULT ''"),
        ("cinemas",  "lat",      "FLOAT"),
        ("cinemas",  "lng",      "FLOAT"),
        ("users",    "telefono",       "VARCHAR(30)  NOT NULL DEFAULT ''"),
        ("users",    "email",          "VARCHAR(120) NOT NULL DEFAULT ''"),
        ("users",    "password_plain", "VARCHAR(200) NOT NULL DEFAULT ''"),
    ]
    with db.engine.connect() as conn:
        for table, col, col_def in _migrations:
            try:
                conn.execute(db.text(f'ALTER TABLE {table} ADD COLUMN "{col}" {col_def}'))
                conn.commit()
                print(f"✅ Migrazione: {table}.{col} aggiunta")
            except Exception:
                conn.rollback()  # colonna già presente, ignora
    admin = db.session.execute(db.select(User).filter_by(username="admin")).scalar()
    if not admin:
        admin = User(username="admin", password_hash=generate_password_hash("admin1234"), password_plain="admin1234", role="admin")
        db.session.add(admin)
        db.session.commit()
        print("✅ Utente admin creato automaticamente (username: admin / password: admin1234)")
    # Seed cinema — inserisce solo quelli mancanti (funziona su DB vuoto e già popolato)
    _cinemas_seed = [
        {"nome": "Cinema Chiusi",                        "città": "Chiusi",                   "num_sale": 6, "telefono": "0578 275077", "indirizzo": "Loc. Querce al Pino, SP 146, 53043 Chiusi SI",         "lat": 43.0025, "lng": 11.9481},
        {"nome": "Cinema Empoli",                        "città": "Empoli",                   "num_sale": 3, "telefono": "0571 72023",  "indirizzo": "Via Cosimo Ridolfi 75, 50053 Empoli FI",              "lat": 43.7208, "lng": 10.9478},
        {"nome": "Cinema Firenze",                       "città": "Firenze",                  "num_sale": 1, "telefono": "055 483607",  "indirizzo": "Via G. Romagnosi 46, 50134 Firenze FI",               "lat": 43.7835, "lng": 11.2427},
        {"nome": "Cinema Odeon",                         "città": "Firenze",                  "num_sale": 1, "telefono": "055 214068",  "indirizzo": "Piazza degli Strozzi 2, 50123 Firenze FI",            "lat": 43.7711, "lng": 11.2519},
        {"nome": "Cinema Grosseto",                      "città": "Grosseto",                 "num_sale": 4, "telefono": "0564 27069",  "indirizzo": "Via Goffredo Mameli 24, 58100 Grosseto GR",           "lat": 42.7641, "lng": 11.1086},
        {"nome": "Cinema Massa",                         "città": "Massa",                    "num_sale": 7, "telefono": "0585 791105", "indirizzo": "Via Dorsale 11, 54100 Massa MS",                      "lat": 44.0181, "lng": 10.1327},
        {"nome": "Cinema Montecatini",                   "città": "Montecatini Terme",        "num_sale": 4, "telefono": "0572 78510",  "indirizzo": "Piazza Massimo D'Azeglio 5, 51016 Montecatini Terme PT", "lat": 43.8849, "lng": 10.7722},
        {"nome": "Cinema Pisa",                          "città": "Pisa",                     "num_sale": 3, "telefono": "050 5552261", "indirizzo": "Via Piave 47, 56123 Pisa PI",                         "lat": 43.7155, "lng": 10.3986},
        {"nome": "Cinecity Pisa",                        "città": "Pisa",                     "num_sale": 5, "telefono": "392 323 3535","indirizzo": "Piazza della Stazione 16, 56125 Pisa PI",             "lat": 43.7090, "lng": 10.3972},
        {"nome": "Cinema Sansepolcro",                   "città": "Sansepolcro",              "num_sale": 1, "telefono": "0575 733433", "indirizzo": "Via XX Settembre 156, 52037 Sansepolcro AR",           "lat": 43.5695, "lng": 12.1406},
        {"nome": "ELIA ANTICA MULTISALA",                "città": "Grosseto",                 "num_sale": 4, "telefono": "0564 644987", "indirizzo": "Via Aurelia Antica 46, 58100 Grosseto GR",            "lat": 42.7548, "lng": 11.0931},
        {"nome": "Cinema Scuderie Granducali Seravezza", "città": "Seravezza",                "num_sale": 1, "telefono": "0584 840409", "indirizzo": "Viale Leonetto Amedei 124, 55047 Seravezza LU",       "lat": 43.9962, "lng": 10.2321},
        {"nome": "Teatro Cinema Giotto",                 "città": "Borgo San Lorenzo",        "num_sale": 1, "telefono": "055 845 9658","indirizzo": "Corso Giacomo Matteotti 151, 50032 Borgo San Lorenzo FI", "lat": 43.9548, "lng": 11.3855},
        {"nome": "Cinema Metropolitan",                  "città": "Piombino",                 "num_sale": 1, "telefono": "0565 30385",  "indirizzo": "Piazza Cappelletti 2, 57025 Piombino LI",             "lat": 42.9225, "lng": 10.5320},
        {"nome": "Cinema Multisala Excelsior",           "città": "Montecatini Terme",        "num_sale": 2, "telefono": "0572 904289", "indirizzo": "Viale Giuseppe Verdi 66, 51016 Montecatini Terme PT", "lat": 43.8825, "lng": 10.7740},
        {"nome": "Cinema Teatro Scipione Ammirato",      "città": "Montaione",                "num_sale": 1, "telefono": "0571 61517",  "indirizzo": "Piazza Gramsci 2, 50050 Montaione FI",                "lat": 43.5595, "lng": 10.9126},
        {"nome": "Multisala Isola Verde",                "città": "Pisa",                     "num_sale": 3, "telefono": "050 973676",  "indirizzo": "Via Vittorio Frascani, 56124 Pisa PI",                "lat": 43.7024, "lng": 10.3912},
        {"nome": "Cinema Sala Esse",                     "città": "Firenze",                  "num_sale": 1, "telefono": "055 666643",  "indirizzo": "Via del Ghirlandaio 38, 50121 Firenze FI",            "lat": 43.7697, "lng": 11.2763},
        {"nome": "Multisala Goldoni",                    "città": "Viareggio",                "num_sale": 2, "telefono": "0584 49832",  "indirizzo": "Via San Francesco 124, 55049 Viareggio LU",           "lat": 43.8682, "lng": 10.2547},
        {"nome": "Cinema Multisala Il Portico",          "città": "Firenze",                  "num_sale": 2, "telefono": "055 669930",  "indirizzo": "Via Capo di Mondo 66, 50136 Firenze FI",              "lat": 43.7698, "lng": 11.2919},
        {"nome": "Cinema Teatro Everest Galluzzo",       "città": "Firenze",                  "num_sale": 1, "telefono": "055 232 1754","indirizzo": "Via Volterrana 4, 50124 Firenze FI",                  "lat": 43.7388, "lng": 11.2413},
        {"nome": "Spazio Alfieri Cinema Teatro Bistrò",  "città": "Firenze",                  "num_sale": 1, "telefono": "055 5320840", "indirizzo": "Via dell'Ulivo 8, 50122 Firenze FI",                  "lat": 43.7703, "lng": 11.2639},
        {"nome": "Cinema Teatro Multisala Imperiale",    "città": "Montecatini Terme",        "num_sale": 4, "telefono": "0572 508601", "indirizzo": "Piazza Massimo D'Azeglio 5, 51016 Montecatini Terme PT", "lat": 43.8849, "lng": 10.7722},
        {"nome": "Cinema Centrale",                      "città": "Viareggio",                "num_sale": 1, "telefono": "0584 581226", "indirizzo": "Via Cesare Battisti 67, 55049 Viareggio LU",          "lat": 43.8707, "lng": 10.2534},
        {"nome": "Cinema Nuova Aurora",                  "città": "Sansepolcro",              "num_sale": 1, "telefono": "0575 1480629","indirizzo": "Via Piero della Francesca 47, 52037 Sansepolcro AR",  "lat": 43.5696, "lng": 12.1393},
        {"nome": "Cinema Marconi",                       "città": "Firenze",                  "num_sale": 3, "telefono": "055 680554",  "indirizzo": "Viale Giannotti 45r, 50126 Firenze FI",               "lat": 43.7526, "lng": 11.2694},
        {"nome": "Multisala Splendor",                   "città": "Massa",                    "num_sale": 7, "telefono": "0585 791105", "indirizzo": "Via Dorsale 11, 54100 Massa MS",                      "lat": 44.0181, "lng": 10.1327},
        {"nome": "Teatro dei Servi",                     "città": "Massa",                    "num_sale": 1, "telefono": "0585 811973", "indirizzo": "Via Palestro 37, 54100 Massa MS",                     "lat": 44.0300, "lng": 10.1406},
        {"nome": "Multisala Odeon",                      "città": "Pisa",                     "num_sale": 4, "telefono": "050 540168",  "indirizzo": "Piazza S. Paolo all'Orto 18, 56127 Pisa PI",          "lat": 43.7188, "lng": 10.4040},
        {"nome": "Cinema Caffè Lanteri",                 "città": "Pisa",                     "num_sale": 1, "telefono": "050 577100",  "indirizzo": "Via San Michele degli Scalzi 46, 56124 Pisa PI",      "lat": 43.7188, "lng": 10.4180},
        {"nome": "Cinema Teatro 4 Mori",                 "città": "Livorno",                  "num_sale": 1, "telefono": "342 543 1247","indirizzo": "Via Pietro Tacca 16, 57123 Livorno LI",               "lat": 43.5498, "lng": 10.3122},
        {"nome": "Multisala Eden",                       "città": "Arezzo",                   "num_sale": 2, "telefono": "0575 353364", "indirizzo": "Via Antonio Guadagnoli 2, 52100 Arezzo AR",            "lat": 43.4632, "lng": 11.8792},
        {"nome": "Nuovo Cinema Caporali",                "città": "Castiglione del Lago",     "num_sale": 3, "telefono": "075 965 3152","indirizzo": "Piazzetta San Domenico 1, 06061 Castiglione del Lago PG", "lat": 43.1200, "lng": 12.0557},
        {"nome": "Cinema Teatro Verdi",                  "città": "San Vincenzo",             "num_sale": 1, "telefono": "0565 701918", "indirizzo": "Via Vittorio Emanuele II 121, 57027 San Vincenzo LI",  "lat": 43.0990, "lng": 10.5398},
        {"nome": "Teatro Signorelli",                    "città": "Cortona",                  "num_sale": 1, "telefono": "0575 601882", "indirizzo": "Piazza Signorelli 13, 52044 Cortona AR",               "lat": 43.2763, "lng": 11.9876},
        {"nome": "Cinema Città di Villafranca",          "città": "Villafranca in Lunigiana", "num_sale": 1, "telefono": "0187 498011", "indirizzo": "Via Roma 2, 54028 Villafranca in Lunigiana MS",        "lat": 44.3035, "lng":  9.9536},
        {"nome": "Cinema Teatro Excelsior",              "città": "Reggello",                 "num_sale": 1, "telefono": "055 869190",  "indirizzo": "Via Dante Alighieri 7, 50066 Reggello FI",            "lat": 43.6845, "lng": 11.5340},
        {"nome": "Cinema Arena Ardenza",                 "città": "Livorno",                  "num_sale": 1, "telefono": "0586 501403", "indirizzo": "Piazza Sforzini 17, 57128 Livorno LI",                "lat": 43.4980, "lng": 10.3350},
        {"nome": "Arena Dentro Le Mura",                 "città": "San Casciano Val di Pesa", "num_sale": 1, "telefono": "",            "indirizzo": "Via Lucardesi 10, 50026 San Casciano Val di Pesa FI", "lat": 43.6563, "lng": 11.1832},
    ]
    _existing_nomi = {c.nome for c in Cinema.query.all()}
    _added = 0
    for c in _cinemas_seed:
        if c["nome"] not in _existing_nomi:
            db.session.add(Cinema(**c))
            _added += 1
    # Aggiorna contatti per cinema già esistenti che non li hanno
    _updated = 0
    _cinema_map = {c.nome: c for c in Cinema.query.all()}
    for s in _cinemas_seed:
        existing = _cinema_map.get(s["nome"])
        if existing and not existing.indirizzo:
            existing.indirizzo = s.get("indirizzo", "")
            existing.telefono  = s.get("telefono", "")
            existing.lat       = s.get("lat")
            existing.lng       = s.get("lng")
            _updated += 1
    if _added or _updated:
        db.session.commit()
        if _added:   print(f"✅ {_added} cinema aggiunti al catalogo")
        if _updated: print(f"✅ {_updated} cinema aggiornati con contatti")
    # Migra cinema dai problemi esistenti non ancora in tabella
    existing_nomi = {c.nome for c in Cinema.query.all()}  # ricarica dopo seed
    for p in Problem.query.all():
        if p.cinema and p.cinema.strip() and p.cinema.strip() not in existing_nomi:
            db.session.add(Cinema(nome=p.cinema.strip(), città="", num_sale=1))
            existing_nomi.add(p.cinema.strip())
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

# --- RESET ADMIN (temporaneo) ---
@app.route("/reset-admin-password-7x9k")
def reset_admin_password():
    admin = db.session.execute(db.select(User).filter_by(username="admin")).scalar()
    if admin:
        admin.password_hash = generate_password_hash("admin1234")
        admin.password_plain = "admin1234"
        admin.role = "admin"
        db.session.commit()
        return "Password admin resettata a 'admin1234'."
    else:
        admin = User(username="admin", password_hash=generate_password_hash("admin1234"), password_plain="admin1234", role="admin")
        db.session.add(admin)
        db.session.commit()
        return "Utente admin ricreato con password 'admin1234'."

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

    # Contatori messaggi e non letti per ogni ticket
    uid = session["user_id"]
    reads = {tr.problem_id: tr.last_read_at
             for tr in TicketRead.query.filter_by(user_id=uid).all()}
    chat_info = {}
    for p in problems:
        total = len(p.comments)
        last_read = reads.get(p.id)
        if last_read is None:
            unread = total
        else:
            unread = sum(1 for c in p.comments if c.data_ora > last_read)
        chat_info[p.id] = {"total": total, "unread": unread}

    return render_template(
        "dashboard.html",
        problems=problems,
        filter_urgenza=filter_urgenza,
        filter_stato=filter_stato,
        stats=stats,
        cinemas=cinemas,
        chat_info=chat_info,
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
    # Segna il ticket come letto dall'utente corrente
    tr = TicketRead.query.filter_by(user_id=session["user_id"], problem_id=p.id).first()
    if tr:
        tr.last_read_at = datetime.utcnow()
    else:
        db.session.add(TicketRead(user_id=session["user_id"], problem_id=p.id))
    db.session.commit()
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

    cinema_nome = request.form.get("cinema", "").strip()
    sala = request.form.get("sala", "1").strip()
    tipo = request.form.get("tipo", "").strip()
    urgenza = request.form.get("urgenza", "Non urgente")
    stato = request.form.get("stato", "Aperto")

    if not cinema_nome or not tipo:
        flash("Compila tutti i campi.", "danger")
        return redirect(url_for("dashboard"))

    # Recupera città dal cinema selezionato
    cinema_obj = Cinema.query.filter_by(nome=cinema_nome).first()
    città = cinema_obj.città if cinema_obj else ""

    p = Problem(
        cinema=cinema_nome,
        città=città,
        sala=sala,
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

# --- ARCHIVIA PROBLEMA (ex elimina) ---
@app.route("/problems/<int:problem_id>/delete", methods=["POST"])
def delete_problem(problem_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    p = db.session.get(Problem, problem_id)
    if not p:
        abort(404)

    if session["role"] != "admin" and session["username"] != p.autore:
        return "Accesso negato", 403

    p.stato = "Chiuso"
    db.session.commit()
    flash("Ticket archiviato.", "success")
    return redirect(url_for("dashboard"))

# --- ELIMINA DEFINITIVAMENTE (solo admin, da ticket archiviato) ---
@app.route("/problems/<int:problem_id>/destroy", methods=["POST"])
def destroy_problem(problem_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session["role"] != "admin":
        return "Accesso negato", 403
    p = db.session.get(Problem, problem_id)
    if not p:
        abort(404)
    db.session.delete(p)
    db.session.commit()
    flash("Ticket eliminato definitivamente.", "success")
    return redirect(url_for("closed_tickets"))

# --- GESTIONE UTENTI ---
@app.route("/users", methods=["GET", "POST"])
def admin_users():
    if session.get("role") != "admin":
        return "Accesso negato", 403

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "user")
        telefono = request.form.get("telefono", "").strip()
        email = request.form.get("email", "").strip()

        if not username or len(password) < 8:
            flash("Username obbligatorio e password di almeno 8 caratteri.", "danger")
            return redirect(url_for("admin_users"))

        existing = db.session.execute(db.select(User).filter_by(username=username)).scalar()
        if existing:
            flash("Username già in uso.", "warning")
            return redirect(url_for("admin_users"))

        u = User(username=username, role=role, password_hash=generate_password_hash(password),
                 password_plain=password, telefono=telefono, email=email)
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
    u.password_plain = new_password
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

    if u.role == "admin" and User.query.filter_by(role="admin").count() <= 1:
        flash("Non puoi eliminare l'unico admin rimasto.", "warning")
        return redirect(url_for("admin_users"))

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
        città = request.form.get("città", "").strip()
        telefono = request.form.get("telefono", "").strip()
        indirizzo = request.form.get("indirizzo", "").strip()
        try:
            num_sale = max(1, int(request.form.get("num_sale", "1")))
        except ValueError:
            num_sale = 1
        if nome:
            db.session.add(Cinema(nome=nome, città=città, num_sale=num_sale,
                                  telefono=telefono, indirizzo=indirizzo))
            db.session.commit()
            flash(f"Cinema '{nome}' ({città}) aggiunto.", "success")
        return redirect(url_for("admin_cinemas"))
    cinemas = Cinema.query.order_by(Cinema.città.asc(), Cinema.nome.asc()).all()
    return render_template("cinemas.html", cinemas=cinemas)

@app.route("/admin/cinemas/<int:cinema_id>/edit", methods=["GET", "POST"])
def edit_cinema(cinema_id):
    if session.get("role") != "admin":
        return "Accesso negato", 403
    c = db.session.get(Cinema, cinema_id)
    if not c:
        abort(404)
    if request.method == "POST":
        nuovo_nome = request.form.get("nome", "").strip()
        nuova_città = request.form.get("città", "").strip()
        num_sale_str = request.form.get("num_sale", "1")
        try:
            num_sale = max(1, int(num_sale_str))
        except ValueError:
            num_sale = 1
        lat_str = request.form.get("lat", "").strip()
        lng_str = request.form.get("lng", "").strip()
        try:
            lat = float(lat_str) if lat_str else None
            lng = float(lng_str) if lng_str else None
        except ValueError:
            lat = None
            lng = None
        if nuovo_nome:
            c.nome = nuovo_nome
            c.città = nuova_città
            c.num_sale = num_sale
            c.telefono = request.form.get("telefono", "").strip()
            c.indirizzo = request.form.get("indirizzo", "").strip()
            c.lat = lat
            c.lng = lng
            db.session.commit()
            flash(f"Cinema '{nuovo_nome}' aggiornato.", "success")
        return redirect(url_for("admin_cinemas"))
    return render_template("edit_cinema.html", c=c)

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
