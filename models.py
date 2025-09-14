# models.py
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    # NB: tabella predefinita sarà "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user")  # "user" | "admin"

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.role})>"


class Problem(db.Model):
    # NB: tabella predefinita sarà "problem"
    id = db.Column(db.Integer, primary_key=True)

    # Campo non più usato in UI: lo lasciamo opzionale per compatibilità DB
    cinema = db.Column(db.String(100), nullable=True)

    sala = db.Column(db.String(50), nullable=False)
    tipo = db.Column(db.Text, nullable=False)
    urgenza = db.Column(db.String(20), nullable=False)  # "Non urgente" | "Urgente" | "Critico"
    stato = db.Column(db.String(20), nullable=False, default="Aperto")
    autore = db.Column(db.String(100), nullable=False)

    # NUOVO: data e ora di apertura del ticket
    apertura = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        ap = self.apertura.strftime("%Y-%m-%d %H:%M") if self.apertura else "-"
        return f"<Problem #{self.id} sala={self.sala} urgenza={self.urgenza} apertura={ap}>"
