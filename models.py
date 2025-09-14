# models.py
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user")

class Problem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sala = db.Column(db.String(50), nullable=False)
    tipo = db.Column(db.String(50), nullable=False)        # ← varchar(50) come nel DB
    urgenza = db.Column(db.String(20), nullable=False)
    stato = db.Column(db.String(20), nullable=False, default="Aperto")
    autore = db.Column(db.String(50), nullable=False)       # ← varchar(50) come nel DB
    apertura = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
