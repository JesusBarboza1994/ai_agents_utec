"""Registra, lista o borra el webhook de Trello que avisa a Clemente cuando una tarjeta pasa a Resuelto.

Uso:
    python scripts/registrar_webhook_trello.py listar
    python scripts/registrar_webhook_trello.py registrar https://<tu-app>/api/webhook/trello
    python scripts/registrar_webhook_trello.py borrar <id_del_webhook>

Lee TRELLO_API_KEY, TRELLO_TOKEN y TRELLO_TABLERO del .env y no imprime la clave ni el token. La URL se registra tal
cual y la app tiene que estar desplegada y respondiendo: Trello la comprueba con un HEAD al registrarla. En la app,
TRELLO_WEBHOOK_URL tiene que valer exactamente esa URL, porque la firma de cada llamada se calcula con ella.
"""
import os
import sys

import requests
from dotenv import load_dotenv

API = "https://api.trello.com/1"


def _credenciales() -> dict:
    """Clave y token de Trello del entorno; termina el programa si falta alguno."""
    clave, token = os.getenv("TRELLO_API_KEY", ""), os.getenv("TRELLO_TOKEN", "")
    if not (clave and token):
        raise SystemExit("Faltan TRELLO_API_KEY y TRELLO_TOKEN en el .env")
    return {"key": clave, "token": token}


def _id_del_tablero(credenciales: dict) -> str:
    """El id del tablero que se llama como TRELLO_TABLERO; termina el programa si no aparece."""
    nombre = os.getenv("TRELLO_TABLERO", "Incidencias Clemente")
    respuesta = requests.get(f"{API}/members/me/boards", params={**credenciales, "fields": "name"}, timeout=15)
    respuesta.raise_for_status()
    for tablero in respuesta.json():
        if tablero["name"] == nombre:
            return tablero["id"]
    raise SystemExit(f"No encontre el tablero {nombre!r} en esa cuenta de Trello")


def listar(credenciales: dict) -> None:
    """Muestra los webhooks de este token: id, URL registrada y si estan activos."""
    respuesta = requests.get(f"{API}/tokens/{credenciales['token']}/webhooks", params={"key": credenciales["key"]}, timeout=15)
    respuesta.raise_for_status()
    webhooks = respuesta.json()
    for w in webhooks:
        print(f"{w['id']}  activo={w.get('active')}  {w['callbackURL']}  ({w.get('description', '')})")
    if not webhooks:
        print("No hay webhooks registrados con este token.")


def registrar(credenciales: dict, url: str) -> None:
    """Registra el webhook del tablero apuntando a `url`; Trello comprueba la URL con un HEAD."""
    if not url.startswith("https://"):
        raise SystemExit("La URL tiene que ser https://: Trello no acepta otra cosa en un servidor publico")
    respuesta = requests.post(f"{API}/webhooks", params={
        **credenciales, "callbackURL": url, "idModel": _id_del_tablero(credenciales),
        "description": "Clemente: avisar al cliente cuando una tarjeta pasa a Resuelto",
    }, timeout=15)
    if respuesta.status_code >= 400:
        raise SystemExit(f"Trello rechazo el registro ({respuesta.status_code}): {respuesta.text[:200]}")
    print(f"Webhook registrado: id {respuesta.json()['id']}")


def borrar(credenciales: dict, id_webhook: str) -> None:
    """Borra un webhook por su id."""
    respuesta = requests.delete(f"{API}/webhooks/{id_webhook}", params=credenciales, timeout=15)
    if respuesta.status_code >= 400:
        raise SystemExit(f"Trello rechazo el borrado ({respuesta.status_code}): {respuesta.text[:200]}")
    print("Webhook borrado.")


def main(argumentos: list[str]) -> None:
    """Despacha el subcomando recibido: listar, registrar <url> o borrar <id>."""
    load_dotenv()
    if argumentos[:1] == ["listar"]:
        listar(_credenciales())
    elif argumentos[:1] == ["registrar"] and len(argumentos) == 2:
        registrar(_credenciales(), argumentos[1])
    elif argumentos[:1] == ["borrar"] and len(argumentos) == 2:
        borrar(_credenciales(), argumentos[1])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
