"""Cierre de un caso desde Trello: cuando el personal mueve la tarjeta a "Resuelto", el cliente recibe el aviso.

Trello llama a un webhook cada vez que algo cambia en el tablero. Aqui se reconoce el unico cambio que interesa
(una tarjeta que pasa a la lista Resuelto), se identifica el caso por el codigo del titulo de la tarjeta (I-XXXXXX
o G-XXXXXX) y se avisa a la conversacion que lo origino con el mismo servicio que usa la decision del personal.

Reglas que conserva:
- Solo se acepta una llamada firmada por Trello; sin secreto configurado no se acepta ninguna.
- Un caso se avisa una sola vez: mover la tarjeta de ida y vuelta, o un reintento de Trello, no repiten el mensaje.
- El aviso es un mensaje libre de WhatsApp: llega mientras el cliente haya escrito en las ultimas 24 horas.
- Un caso del webchat no sale por Twilio: el aviso queda en la bandeja de su navegador, que el chat recoge solo.
- Lo que hizo el equipo llega al cliente solo si alguien lo escribio para el: un comentario de la tarjeta que empieza
  con "Para el cliente:". Las notas internas (las del equipo y las que deja Clemente) nunca salen. Sin ese comentario
  se manda el aviso generico. El texto es una plantilla, sin modelo, y pasa por la validacion de salida del aviso.
- Un aviso entregado anula el resumen de reserva que estuviera esperando confirmacion, igual que lo anula cualquier
  mensaje nuevo: si no, un "si" a "¿quedo resuelta tu consulta?" confirmaria esa reserva sin que el cliente lo quisiera.
"""
import base64
import hashlib
import hmac
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import requests

from ...datos import carpeta_de_datos
from ...incidencias.codigos import codigo_admitido
from ...incidencias.servicio_json import ServicioIncidenciasJSON
from ...observabilidad.trazas import registrar
from . import aviso_staff_service

LISTA_RESUELTO = "resuelto"
ARCHIVO_AVISOS = carpeta_de_datos(Path(__file__).resolve().parents[2] / "incidencias" / "datos") / "avisos_cierre.json"
TEXTO_CIERRE = ("¡Listo! Tu caso {codigo} ya fue resuelto por el equipo del restaurante ✅ "
                "Si necesitas algo más, aquí estamos.")
# Con lo que el equipo escribio para el cliente, segun el tipo de caso.
CIERRE_RECLAMO = "¡Listo! Revisamos tu caso {codigo}{sobre}. Lo que hicimos: {resolucion}. Gracias por avisarnos ✅"
CIERRE_PEDIDO_DE_PERSONA = ("¡Listo! El equipo atendió tu pedido {codigo}: {resolucion}. ¿Quedó resuelta tu consulta? "
                            "Si falta algo, cuéntame aquí 😊")
CIERRE_CON_RESOLUCION = "¡Listo! Tu caso {codigo} ya fue resuelto por el equipo del restaurante: {resolucion} ✅"
PREFIJO_PARA_EL_CLIENTE = "para el cliente:"
TIPOS_DE_RECLAMO = {"espera", "servicio", "producto"}
LARGO_MAXIMO_RESOLUCION = 400
LARGO_MAXIMO_RESUMEN = 80
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


def resolucion_para_el_cliente(id_tarjeta: str) -> str | None:
    """El comentario mas reciente de la tarjeta que empieza con "Para el cliente:", sin el prefijo; None si no hay.

    Usa las credenciales de Trello de la app. Si faltan o Trello no responde, devuelve None y el cliente recibe el
    aviso generico: que la resolucion no se pueda leer no impide avisar que el caso se cerro."""
    clave, token = os.getenv("TRELLO_API_KEY", ""), os.getenv("TRELLO_TOKEN", "")
    if not (id_tarjeta and clave and token):
        return None
    try:
        respuesta = requests.get(f"https://api.trello.com/1/cards/{id_tarjeta}/actions",
                                 params={"key": clave, "token": token, "filter": "commentCard"}, timeout=10)
        respuesta.raise_for_status()
        comentarios = respuesta.json()
    except Exception as error:
        registrar("error", "trello", detalle={"paso": "leer_resolucion", "error": type(error).__name__})
        return None
    for comentario in comentarios if isinstance(comentarios, list) else []:      # Trello los da del mas reciente
        texto = str(((comentario or {}).get("data") or {}).get("text") or "").strip()
        if texto.lower().startswith(PREFIJO_PARA_EL_CLIENTE):
            resolucion = " ".join(texto[len(PREFIJO_PARA_EL_CLIENTE):].split()).rstrip(" .")
            return resolucion[:LARGO_MAXIMO_RESOLUCION] or None
    return None


def _resumen_del_reclamo(descripcion: str) -> str:
    """La primera linea del caso, corta y sin las marcas internas, para recordarle al cliente de que se trataba."""
    primera = (descripcion or "").splitlines()[0].strip() if descripcion else ""
    if not primera or primera.startswith("["):
        return ""
    if len(primera) > LARGO_MAXIMO_RESUMEN:
        primera = primera[:LARGO_MAXIMO_RESUMEN].rsplit(" ", 1)[0] + "…"
    return f" ({primera.rstrip('.')})"


def texto_de_cierre(caso, codigo: str, resolucion: str | None) -> str:
    """El aviso para el cliente: con lo que hizo el equipo si lo escribio, segun el tipo de caso; si no, el generico."""
    if not resolucion:
        return TEXTO_CIERRE.format(codigo=codigo)
    if caso.tipo in TIPOS_DE_RECLAMO:
        return CIERRE_RECLAMO.format(codigo=codigo, sobre=_resumen_del_reclamo(caso.descripcion), resolucion=resolucion)
    if caso.tipo == "otro":
        return CIERRE_PEDIDO_DE_PERSONA.format(codigo=codigo, resolucion=resolucion)
    return CIERRE_CON_RESOLUCION.format(codigo=codigo, resolucion=resolucion)


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


def _anular_resumen_pendiente(sesion_id: str) -> None:
    """Descarta el resumen que esperaba confirmacion: el ultimo mensaje que vio el cliente ya no es ese resumen.

    Un fallo se traza y no interrumpe el aviso, que ya salio."""
    from ...agentes import autorizacion          # al usarlo: los servicios de comunicacion no cargan los agentes al importar

    try:
        autorizacion.descartar(sesion_id)
    except Exception as error:
        registrar("error", sesion_id, detalle={"paso": "anular_resumen_por_aviso", "error": type(error).__name__})


def _guardar_cierre_en_local(codigo: str) -> None:
    """Deja el caso cerrado en el registro local: si despues Trello no responde, el pedido ya no cuenta como abierto.

    Un fallo se traza y no interrumpe el aviso."""
    try:
        ServicioIncidenciasJSON().actualizar_estados({codigo: "cerrada"})
    except Exception as error:
        registrar("error", "trello", detalle={"paso": "guardar_cierre_en_local", "error": type(error).__name__})


def avisar_cierre(carga: dict) -> dict:
    """Avisa al cliente que su caso se cerro, si la llamada de Trello es un cierre y el caso aun no se aviso.

    Antes de avisar deja el caso cerrado en el registro local. Devuelve `{"estado", ...}`: `ignorado` (no era un
    cierre o el caso no existe), `ya_avisado`, `enviado` o `no_enviado` (con el motivo). No lanza por un fallo del
    envio."""
    codigo = codigo_del_cierre(carga)
    if not codigo:
        return {"estado": "ignorado", "motivo": "no es el cierre de un caso"}

    with _candado:
        _guardar_cierre_en_local(codigo)
        if codigo in _leer_avisados():
            return {"estado": "ya_avisado", "codigo": codigo}
        caso = next((c for c in ServicioIncidenciasJSON().listar_incidencias() if c.id == codigo), None)
        if caso is None:
            registrar("cierre_trello_ignorado", "trello", detalle={"codigo": codigo, "motivo": "caso desconocido"})
            return {"estado": "ignorado", "motivo": "caso desconocido", "codigo": codigo}
        id_tarjeta = ((((carga.get("action") or {}).get("data") or {}).get("card")) or {}).get("id", "")
        texto = texto_de_cierre(caso, codigo, resolucion_para_el_cliente(id_tarjeta))
        resultado = aviso_staff_service.avisar_decision(caso.sesion_id, texto)
        if resultado["estado"] == aviso_staff_service.ENVIADO:
            _marcar_avisado(codigo)
            _anular_resumen_pendiente(caso.sesion_id)
        registrar("cierre_trello", caso.sesion_id, detalle={"codigo": codigo, "estado": resultado["estado"],
                                                            "motivo": resultado["motivo"]})
    return {"codigo": codigo, "estado": resultado["estado"], "motivo": resultado["motivo"]}
