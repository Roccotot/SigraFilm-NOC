from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash
from models import db, User

# --- RESET PASSWORD (solo admin) ---
@app.route("/users/<int:user_id>/reset", methods=["POST"])
def reset_password(user_id):
    if session.get("role") != "admin":
        return "Accesso negato", 403

    new_password = request.form.get("new_password", "").strip()
    if len(new_password) < 8:
        flash("La nuova password deve avere almeno 8 caratteri.", "danger")
        return redirect(url_for("users"))

    u = User.query.get_or_404(user_id)
    u.password_hash = generate_password_hash(new_password)
    db.session.commit()
    flash(f"Password di '{u.username}' aggiornata con successo.", "success")
    return redirect(url_for("users"))

# --- ELIMINA UTENTE (solo admin) ---
@app.route("/users/<int:user_id>/delete", methods=["POST"])
def delete_user(user_id):
    if session.get("role") != "admin":
        return "Accesso negato", 403

    # opzionale: impedisci all’admin di cancellare se stesso mentre è loggato
    if session.get("user_id") == user_id:
        flash("Non puoi eliminare il tuo utente mentre sei loggato.", "warning")
        return redirect(url_for("users"))

    u = User.query.get_or_404(user_id)
    username = u.username
    db.session.delete(u)
    db.session.commit()
    flash(f"Utente '{username}' eliminato.", "success")
    return redirect(url_for("users"))
