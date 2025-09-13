import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from datetime import datetime

# -----------------------------------------------------------------------------
# CONFIGURAZIONE APP
# -----------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")

# -----------------------------------------------------------------------------
# DATABASE
# -----------------------------------------------------------------------------
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://sigrafilm_db_user:password@localhost:5432/sigrafilm_db"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="user")
    created_at = Column(DateTime, default=datetime.utcnow)

    issues = relationship("Issue", back_populates="author")


class Issue(Base):
    __tablename__ = "issues"

    id = Column(Integer, primary_key=True)
    room = Column(String, nullable=False)
    cinema = Column(String, nullable=False)
    kind = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    urgency = Column(String, nullable=False)
    status = Column(String, default="In corso")
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    author = relationship("User", back_populates="issues")


# Crea le tabelle se non esistono
Base.metadata.create_all(bind=engine)


# -----------------------------------------------------------------------------
# UTILITY
# -----------------------------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user():
    if "user_id" in session:
        db = SessionLocal()
        return db.query(User).filter(User.id == session["user_id"]).first()
    return None


# -----------------------------------------------------------------------------
# ROUTES
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    db = SessionLocal()
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        # Admin "hardcoded"
        if username == "admin" and password == "SigraFilm2025":
            session["user_id"] = -1
            session["role"] = "admin"
            return redirect(url_for("dashboard"))

        user = db.query(User).filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session["user_id"] = user.id
            session["role"] = user.role
            return redirect(url_for("dashboard"))

        flash("Credenziali non valide", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
    db = SessionLocal()
    if session.get("role") == "admin":
        issues = db.query(Issue).all()
    else:
        issues = db.query(Issue).filter_by(author_id=session.get("user_id")).all()
    return render_template("dashboard.html", issues=issues, user=current_user())


@app.route("/issues/new", methods=["GET", "POST"])
def new_issue():
    db = SessionLocal()
    if request.method == "POST":
        issue = Issue(
            room=request.form["room"],
            cinema=request.form["cinema"],
            kind=request.form["kind"],
            description=request.form["description"],
            urgency=request.form["urgency"],
            author_id=session.get("user_id"),
        )
        db.add(issue)
        db.commit()
        flash("Problema aggiunto!", "success")
        return redirect(url_for("dashboard"))
    return render_template("edit_issue.html")


@app.route("/issues/<int:issue_id>/edit", methods=["GET", "POST"])
def edit_issue(issue_id):
    db = SessionLocal()
    issue = db.query(Issue).get(issue_id)
    if request.method == "POST":
        issue.room = request.form["room"]
        issue.cinema = request.form["cinema"]
        issue.kind = request.form["kind"]
        issue.description = request.form["description"]
        issue.urgency = request.form["urgency"]
        issue.status = request.form["status"]
        db.commit()
        flash("Problema aggiornato!", "success")
        return redirect(url_for("dashboard"))
    return render_template("edit_issue.html", issue=issue)


@app.route("/issues/<int:issue_id>/delete")
def delete_issue(issue_id):
    db = SessionLocal()
    issue = db.query(Issue).get(issue_id)
    if issue:
        db.delete(issue)
        db.commit()
        flash("Problema eliminato!", "success")
    return redirect(url_for("dashboard"))


# ---------------------- ADMIN: GESTIONE UTENTI ----------------------
@app.route("/admin/users")
def admin_users():
    if session.get("role") != "admin":
        return redirect(url_for("dashboard"))
    db = SessionLocal()
    users = db.query(User).all()
    return render_template("admin_users.html", users=users)


@app.route("/admin/users/new", methods=["GET", "POST"])
def new_user():
    if session.get("role") != "admin":
        return redirect(url_for("dashboard"))
    db = SessionLocal()
    if request.method == "POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"])
        role = request.form["role"]
        user = User(username=username, password_hash=password, role=role)
        db.add(user)
        db.commit()
        flash("Utente aggiunto!", "success")
        return redirect(url_for("admin_users"))
    return render_template("edit_user.html")


@app.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
def edit_user(user_id):
    if session.get("role") != "admin":
        return redirect(url_for("dashboard"))
    db = SessionLocal()
    user = db.query(User).get(user_id)
    if request.method == "POST":
        user.username = request.form["username"]
        if request.form["password"]:
            user.password_hash = generate_password_hash(request.form["password"])
        user.role = request.form["role"]
        db.commit()
        flash("Utente aggiornato!", "success")
        return redirect(url_for("admin_users"))
    return render_template("edit_user.html", user=user)


@app.route("/admin/users/<int:user_id>/delete")
def delete_user(user_id):
    if session.get("role") != "admin":
        return redirect(url_for("dashboard"))
    db = SessionLocal()
    user = db.query(User).get(user_id)
    if user:
        db.delete(user)
        db.commit()
        flash("Utente eliminato!", "success")
    return redirect(url_for("admin_users"))


# -----------------------------------------------------------------------------
# AVVIO
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
