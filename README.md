# 🎬 SigraFilm NOC Dashboard

Applicazione web per la gestione dei problemi tecnici nei cinema **SigraFilm**.  
Sviluppata con **Flask**, **PostgreSQL** e **Bootstrap**.

## 🚀 Funzionalità

- 🔑 **Login/Logout** con ruoli:
  - **Admin** → gestisce utenti e vede tutti i problemi.
  - **Utente** → può aggiungere, modificare ed eliminare solo i propri problemi.
- 📝 **Segnalazione problemi** con:
  - Cinema
  - Descrizione
  - Urgenza (Non urgente / Urgente / Critico)
  - Stato (Aperto / In corso / Chiuso)
  - Data e ora registrazione
- 📊 **Dashboard**:
  - Tabella ordinabile per ogni colonna
  - Evidenziazione righe in base all’urgenza
  - Filtri per urgenza e stato
- 👥 **Gestione utenti (solo admin)**:
  - Creazione utenti con ruolo (`user` o `admin`)
  - Reset password
  - Eliminazione utenti

## 🛠️ Tecnologie

- [Flask](https://flask.palletsprojects.com/) – backend Python
- [Flask-SQLAlchemy](https://flask-sqlalchemy.palletsprojects.com/) – ORM
- [PostgreSQL](https://www.postgresql.org/) – database
- [Bootstrap 5](https://getbootstrap.com/) – frontend responsive
- [Gunicorn](https://gunicorn.org/) – application server

## 📂 Struttura progetto

