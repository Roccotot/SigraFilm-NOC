# main.py
# Questo file esiste solo per compatibilità con Render
# in modo che il comando "gunicorn main:app" trovi l'applicazione Flask.

from app import app

# Se vuoi testare in locale, puoi avviarlo anche direttamente:
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
