"""Cierre de un caso desde Trello: cuando el personal mueve la tarjeta a "Resuelto", el cliente recibe el aviso por WhatsApp.

Trello llama a un webhook cada vez que algo cambia en el tablero. Aqui se reconoce el unico cambio que interesa
(una tarjeta que pasa a la lista Resuelto), se identifica el caso por el codigo del titulo de la tarjeta (I-XXXXXX
o G-XXXXXX) y se avisa a la conversacion que lo origino con el mismo servicio que usa la decision del personal.

Reglas que conserva:
- Solo se acepta una llamada firmada por Trello; sin secreto configurado no se acepta ninguna.
- Un caso se avisa una sola vez: mover la tarjeta de ida y vuelta, o un reintento de Trello, no repiten el mensaje.
- El aviso es un mensaje libre de WhatsApp: llega mientras el cliente haya escrito en las ultimas 24 horas.
- Un caso del webchat no tiene canal de salida: se registra y no se envia nada.
"""
import base64
import hashlib
import hmac
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from ...datos import carpeta_de_datos
from ...incidencias.codigos import codigo_admitido
from ...incidencias.servicio_json import ServicioIncidenciasJSON
from ...observabilidad.trazas import registrar
from . import aviso_staff_service

LISTA_RESUELTO = "resuelto"
ARCHIVO_AVISOS = carpeta_de_datos(Path(__file__).resolve().parents[2] / "incidencias" / "datos") / "avisos_cierre.json"
TEXTO_CIERRE = ("Tu caso {codigo} fue resuelto por el equipo del restaurante. "
                "Si necesitas algo más, escríbenos por aquí.")
# Un solo aviso a la vez: Trello reintenta si tarda, y el segundo intento tiene que ver el primero ya registrado.
_candado = threading.Lock()


def firma_valida(cuerpo: bytes, url: str, firma: str, secreto: str) -> bool:
    """Comprueba la cabecera X-Trello-Webhook: base64 del HMAC-SHA1 del cuerpo mas la URL registrada.

    Devuelve False si falta el secreto, la URL o la firma: sin configuracion no se acepta ninguna llamada."""
    if not (secreto and url and firma):
        return False
    esperada = base64.b64encode(hmac.new(secreto.encode(), cuerpo + url.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(esperada, firma)


def codigo_del_cierre(carga: dict) -> str | None:
    """El codigo del caso si la llamada es una tarjeta que pasa a Resuelto; None para cualquier otro cambio.

    Exige que venga de otra lista (un cambio de lista de verdad) y que el titulo empiece con un codigo valido
    seguido de un punto medio, que es como el servicio de Trello nombra las tarjetas."""
    accion = carga.get("action") or {}
    if accion.get("type") != "updateCard":
        return None
    datos = accion.get("data") or {}
    destino = ((datos.get("listAfter") or {}).get("name") or "").strip().lower()
    if destino != LISTA_RESUELTO or not datos.get("listBefore"):
        return None
    titulo = (datos.get("card") or {}).get("name") or ""
    codigo = titulo.split("·")[0].strip().upper()
    return codigo if codigo_admitido(codigo) else None


def _leer_avisados() -> dict:
    """Los casos ya avisados, con la hora; vacio si el archivo falta o no se puede leer."""
    try:
        datos = json.loads(ARCHIVO_AVISOS.read_text(encoding="utf-8"))
        return datos if isinstance(datos, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _marcar_avisado(codigo: str) -> None:
    """Anota el caso como avisado con archivo temporal y reemplazo; un fallo de escritura se traza y no interrumpe."""
    avisados = _leer_avisados()
    avisados[codigo] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        ARCHIVO_AVISOS.parent.mkdir(parents=True, exist_ok=True)
        temporal = ARCHIVO_AVISOS.with_suffix(".tmp")
        temporal.write_text(json.dumps(avisados, ensure_ascii=False, indent=2), encoding="utf-8")
        temporal.replace(ARCHIVO_AVISOS)
    except OSError as error:
        registrar("error", "trello", detalle={"paso": "marcar_aviso_de_cierre", "error": type(error).__name__})


def avisar_cierre(carga: dict) -> dict:
    """Avisa al cliente que su caso se cerro, si la llamada de Trello es un cierre y el caso aun no se aviso.

    Devuelve `{"estado", ...}`: `ignorado` (no era un cierre o el caso no existe), `ya_avisado`, `enviado`,
    `no_enviado` (con el motivo) o `no_aplica` (webchat). No lanza por un fallo del envio."""
    codigo = codigo_del_cierre(carga)
    if not codigo:
        return {"estado": "ignorado", "motivo": "no es el cierre de un caso"}

    with _candado:
        if codigo in _leer_avisados():
            return {"estado": "ya_avisado", "codigo": codigo}
        caso = next((c for c in ServicioIncidenciasJSON().listar_incidencias() if c.id == codigo), None)
        if caso is None:
            registrar("cierre_trello_ignorado", "trello", detalle={"codigo": codigo, "motivo": "caso desconocido"})
            return {"estado": "ignorado", "motivo": "caso desconocido", "codigo": codigo}
        resultado = aviso_staff_service.avisar_decision(caso.sesion_id, TEXTO_CIERRE.format(codigo=codigo))
        if resultado["estado"] == aviso_staff_service.ENVIADO:
            _marcar_avisado(codigo)
        registrar("cierre_trello", caso.sesion_id, detalle={"codigo": codigo, "estado": resultado["estado"],
                                                            "motivo": resultado["motivo"]})
    return {"codigo": codigo, "estado": resultado["estado"], "motivo": resultado["motivo"]}
