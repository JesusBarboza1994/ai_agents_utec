"""
Punto de entrada de Clemente.

    python run.py            # levanta el servidor en http://localhost:5000
    flask --app run run      # equivalente, usando el CLI de Flask

El servidor sirve tres cosas:
  * el chat de demo (GET /)
  * la API de conversacion (POST /api/chat)  -- lo que consumen los canales
  * los webhooks de cada canal (POST /api/webhook/<canal>)
"""

import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("CLEMENTE_PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "1") == "1",
    )
