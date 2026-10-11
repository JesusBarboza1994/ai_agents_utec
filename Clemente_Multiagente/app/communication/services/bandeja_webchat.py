"""Bandeja de mensajes salientes del webchat: lo que el servidor le dice al cliente sin que este haya escrito.

El webchat no tiene canal de salida como WhatsApp (no hay Twilio). Cuando el personal aprueba o rechaza una solicitud de
grupo, o cierra el caso en Trello, el mensaje se deja aqui y el chat de ese navegador lo recoge solo, consultando cada
pocos segundos (`GET /api/chat/avisos`).

Reglas que conserva:
- Cada navegador ve solo lo suyo: se busca por la sesion firmada en su cookie, nunca por un dato que mande el cliente.
- Entrega con acuse: el chat dice hasta que numero ya mostro (`visto`) y se borra hasta ahi. Lo que no se acuso se
  repite, y el chat descarta los repetidos por su numero.
- Acotada: los ultimos MAXIMO_POR_SESION de cada sesion y MAXIMO_SESIONES sesiones, para que un navegador que nunca
  vuelve no la llene.
- Un fallo de lectura o de escritura nunca interrumpe a quien deposita: el mensaje igual queda en el hilo.
"""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from ...datos import carpeta_de_datos
from ...observabilidad.trazas import registrar

ARCHIVO = carpeta_de_datos(Path(__file__).resolve().parents[2] / "agentes" / "datos") / "bandeja_webchat.json"
MAXIMO_POR_SESION = 20
MAXIMO_SESIONES = 200
# Una sola escritura a la vez dentro del proceso; la lectura va siempre al archivo para ver lo que dejo otro proceso.
_candado = threading.Lock()


def _leer() -> dict:
    """Contenido de la bandeja `{"siguiente": n, "sesiones": {...}}`; vacia si el archivo falta o no se puede leer."""
    try:
        datos = json.loads(ARCHIVO.read_text(encoding="utf-8"))
        if isinstance(datos, dict) and isinstance(datos.get("sesiones"), dict):
            return {"siguiente": int(datos.get("siguiente") or 1), "sesiones": datos["sesiones"]}
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError, TypeError):
        pass
    return {"siguiente": 1, "sesiones": {}}


def _escribir(datos: dict) -> bool:
    """Guarda la bandeja con archivo temporal y reemplazo; False (y una traza) si el disco falla."""
    try:
        ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
        temporal = ARCHIVO.with_suffix(".tmp")
        temporal.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        temporal.replace(ARCHIVO)
        return True
    except OSError as error:
        registrar("error", "bandeja_webchat", detalle={"paso": "escribir_bandeja", "error": type(error).__name__})
        return False


def depositar(sesion_id: str, texto: str) -> int | None:
    """Deja `texto` para el navegador de esa sesion y devuelve su numero; None si no se pudo guardar.

    No lanza. Si la sesion ya tenia MAXIMO_POR_SESION mensajes, se descartan los mas viejos; si hay mas de
    MAXIMO_SESIONES sesiones, se descartan las que llevan mas tiempo sin recibir nada."""
    with _candado:
        datos = _leer()
        numero = datos["siguiente"]
        datos["siguiente"] = numero + 1
        mensajes = datos["sesiones"].setdefault(sesion_id, [])
        mensajes.append({"id": numero, "texto": texto, "hora": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        datos["sesiones"][sesion_id] = mensajes[-MAXIMO_POR_SESION:]
        if len(datos["sesiones"]) > MAXIMO_SESIONES:
            ordenadas = sorted(datos["sesiones"].items(), key=lambda par: par[1][-1]["id"] if par[1] else 0)
            datos["sesiones"] = dict(ordenadas[len(datos["sesiones"]) - MAXIMO_SESIONES:])
        return numero if _escribir(datos) else None


def recoger(sesion_id: str, visto: int = 0) -> list[dict]:
    """Los mensajes de esa sesion con numero mayor que `visto`; antes borra los ya acusados (numero <= visto).

    Cada mensaje es `{"id", "texto", "hora"}`. Sin nada nuevo no escribe en disco."""
    with _candado:
        datos = _leer()
        mensajes = datos["sesiones"].get(sesion_id) or []
        restantes = [m for m in mensajes if isinstance(m, dict) and m.get("id", 0) > visto]
        if len(restantes) != len(mensajes):
            if restantes:
                datos["sesiones"][sesion_id] = restantes
            else:
                datos["sesiones"].pop(sesion_id, None)
            _escribir(datos)
        return restantes


def olvidar(sesion_id: str) -> None:
    """Vacia la bandeja de esa sesion (al reiniciar la conversacion); no hace nada si no tenia."""
    with _candado:
        datos = _leer()
        if datos["sesiones"].pop(sesion_id, None) is not None:
            _escribir(datos)
