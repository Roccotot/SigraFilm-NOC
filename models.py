from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default="user")

class Problem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cinema = db.Column(db.String(50))
    sala = db.Column(db.String(50))
    tipo = db.Column(db.String(50))
    urgenza = db.Column(db.String(20))
    stato = db.Column(db.String(20), default="Aperto")
    autore = db.Column(db.String(50))
