"""Simula la llamada que haria Trello al mover una tarjeta a Resuelto, firmada como Trello, contra una app local.

Sirve para probar el aviso por WhatsApp sin desplegar ni registrar nada en Trello.

Uso:
    python scripts/simular_cierre_trello.py <codigo_del_caso> [url_del_webhook]

Necesita en el .env de la app: TRELLO_SECRET y TRELLO_WEBHOOK_URL (para probar en local, por ejemplo
http://127.0.0.1:5000/api/webhook/trello). El caso tiene que existir, ser de WhatsApp, y el cliente tiene que haber
escrito en las ultimas 24 horas. Si no pasas la URL, se usa TRELLO_WEBHOOK_URL.
"""
import base64
import hashlib
import hmac
import json
import os
import sys

import requests
from dotenv import load_dotenv


def firmar(cuerpo: bytes, url: str, secreto: str) -> str:
    """Firma como Trello: base64 del HMAC-SHA1 del cuerpo mas la URL registrada."""
    return base64.b64encode(hmac.new(secreto.encode(), cuerpo + url.encode(), hashlib.sha1).digest()).decode()


def main(argumentos: list[str]) -> None:
    """Arma el cuerpo de un cierre para el caso indicado, lo firma y lo envia a la app."""
    load_dotenv()
    if not argumentos:
        raise SystemExit(__doc__)
    codigo = argumentos[0].strip().upper()
    secreto, url_firma = os.getenv("TRELLO_SECRET", ""), os.getenv("TRELLO_WEBHOOK_URL", "")
    if not (secreto and url_firma):
        raise SystemExit("Faltan TRELLO_SECRET y TRELLO_WEBHOOK_URL en el .env")
    destino = argumentos[1] if len(argumentos) > 1 else url_firma
    carga = {"action": {"type": "updateCard", "data": {
        "card": {"id": "simulada", "name": f"{codigo} · simulado desde scripts/simular_cierre_trello.py"},
        "listBefore": {"name": "En atencion"}, "listAfter": {"name": "Resuelto"},
    }}}
    cuerpo = json.dumps(carga).encode()
    respuesta = requests.post(destino, data=cuerpo, timeout=30, headers={
        "Content-Type": "application/json", "X-Trello-Webhook": firmar(cuerpo, url_firma, secreto)})
    print(respuesta.status_code, respuesta.text.strip())


if __name__ == "__main__":
    main(sys.argv[1:])
