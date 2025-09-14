from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user")

    def __repr__(self):
        return f"<User {self.username}>"


class Problem(db.Model):
    __tablename__ = "problems"

    id = db.Column(db.Integer, primary_key=True)
    cinema = db.Column(db.String(100), nullable=False)
    sala = db.Column(db.String(50), nullable=False)
    tipo = db.Column(db.Text, nullable=False)  # frasi lunghe
    urgenza = db.Column(db.String(50), nullable=False)
    stato = db.Column(db.String(50), default="Aperto")
    autore = db.Column(db.String(80), nullable=False)
    data_creazione = db.Column(db.DateTime, default=datetime.utcnow)  # 👈 data e ora

    def __repr__(self):
        return f"<Problem {self.id} - {self.tipo[:20]}>"
