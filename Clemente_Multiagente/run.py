"""
Punto de entrada de Clemente.

    python run.py            # levanta el servidor en http://localhost:5000
    flask --app run run      # equivalente, usando el CLI de Flask

El servidor sirve tres cosas:
  * el chat de demo (GET /)
  * la API de conversacion (POST /api/chat)  -- lo que consumen los canales
  * el webhook de WhatsApp (POST /api/webhook/whatsapp)
"""

import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("CLEMENTE_PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "1") == "1",
        # Sin esto el servidor dev de Werkzeug atiende una conexion a la vez:
        # dos clientes reales pidiendo la misma mesa a la vez se procesarian
        # en cola, no en paralelo, y el lock de Postgres nunca se ejercitaria
        # de verdad (visible al correr scripts/benchmark_reservas.py sin esto).
        threaded=True,
    )
