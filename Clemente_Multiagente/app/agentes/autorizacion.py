"""Autorizacion local: propiedad por sesion y confirmaciones fuera del LLM.

El telefono y los argumentos de tools NO son identidad. Las reservas antiguas
sin vinculacion requieren recuperacion por personal; no se adjudican por codigo.
SQLite guarda permisos/propuestas, no reemplaza el gestor de reservas de Miguel.
"""
import json
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

ARCHIVO = Path(__file__).parent / "datos" / "autorizaciones.sqlite3"
VIGENCIA_SEGUNDOS = 600
_lock = RLock()
DENEGADO = "No puedo acceder a esa reserva desde esta conversación. Solicita al restaurante que verifique tu identidad para recuperarla."


@contextmanager
def _db():
    """Abre SQLite, crea las tablas de propiedad y propuestas si faltan y cede la conexion.

    Confirma la transaccion al salir normalmente, la revierte ante error y
    cierra siempre la conexion. Los errores de SQLite se propagan."""
    ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(ARCHIVO, timeout=10)
    try:
        db.execute("CREATE TABLE IF NOT EXISTS propietarios (reserva TEXT PRIMARY KEY, sesion TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS propuestas (sesion TEXT PRIMARY KEY, codigo TEXT NOT NULL, accion TEXT NOT NULL, datos TEXT NOT NULL, vence REAL NOT NULL)")
        with db:
            yield db
    finally:
        db.close()


def vincular(sesion, reserva_id):
    """Persiste la propiedad de reserva_id para sesion.

    Rechaza sesiones vacias, desconocida o studio con ValueError; una reserva
    ya vinculada produce el error de integridad de SQLite."""
    if not sesion or sesion in {"desconocida", "studio"}:
        raise ValueError("Sesion no identificada")
    with _db() as db:
        db.execute("INSERT INTO propietarios VALUES (?, ?)", (reserva_id, sesion))


def es_propietario(sesion, reserva_id):
    """Devuelve si SQLite vincula exactamente reserva_id con sesion; no usa el telefono."""
    with _db() as db:
        return db.execute("SELECT 1 FROM propietarios WHERE reserva=? AND sesion=?", (reserva_id, sesion)).fetchone() is not None


def reservas_propias(sesion, servicio):
    """Devuelve las reservas vinculadas a sesion que todavia existen en servicio.

    Incluye sus estados actuales, tambien canceladas; omite codigos inexistentes."""
    with _db() as db:
        ids = [r[0] for r in db.execute("SELECT reserva FROM propietarios WHERE sesion=?", (sesion,))]
    return [r for codigo in ids if (r := servicio.obtener_reserva(codigo)) is not None]


def descartar(sesion):
    """Elimina la propuesta pendiente de sesion sin borrar la propiedad de sus reservas."""
    with _db() as db:
        db.execute("DELETE FROM propuestas WHERE sesion=?", (sesion,))


def proponer(contexto, accion, datos, servicio):
    """Prepara crear, modificar o cancelar sin escribir una reserva en el servicio.

    contexto aporta la sesion del servidor; datos contiene los parametros
    de la operacion. Comprueba propiedad para modificar/cancelar y captura
    el registro anterior. Para crear/modificar exige fecha no pasada y de
    1 a 10 personas; crear tambien exige contacto y disponibilidad.

    Persiste en SQLite una propuesta por sesion con token y vencimiento,
    y guarda confirmacion_pendiente en contexto.datos. Devuelve el resumen
    del servidor con CONFIRMO o el motivo de rechazo. Una accion desconocida
    produce ValueError; otros errores de servicio o persistencia se propagan.
    """
    sesion = contexto.sesion_id
    if not sesion or sesion in {"desconocida", "studio"}:
        return "No se puede preparar una operación sin una sesión identificada. Usa el chat."
    datos = dict(datos)
    if accion in {"modificar", "cancelar"}:
        codigo = datos["reserva_id"]
        if not es_propietario(sesion, codigo):
            contexto.datos["guardrail_autorizacion"] = {"estado": "bloqueado"}
            return DENEGADO
        actual = servicio.obtener_reserva(codigo)
        if actual is None or actual.estado == "cancelada":
            return "La reserva no está vigente. No se realizó ningún cambio."
        datos["anterior"] = actual.__dict__
    elif accion != "crear":
        raise ValueError("Operacion desconocida")

    if accion != "cancelar":
        anterior = datos.get("anterior", {})
        fecha = datos.get("fecha") or anterior.get("fecha")
        hora = datos.get("hora") or anterior.get("hora")
        personas = datos.get("personas") or anterior.get("personas")
        if not isinstance(personas, int) or not 1 <= personas <= 10:
            return "No se preparó la reserva: admite de 1 a 10 personas; grupos mayores requieren coordinación con el restaurante."
        from datetime import date
        try:
            if date.fromisoformat(fecha) < date.today():
                raise ValueError()
        except (ValueError, TypeError):
            return "Indica una fecha válida que no esté en el pasado."
        if accion == "crear" and (not datos["nombre"].strip() or not datos["telefono"].strip()):
            return "Faltan el nombre y/o el teléfono de contacto."
        if accion == "crear" and not servicio.consultar_disponibilidad(fecha, hora, personas, datos.get("zona") or None):
            return "No hay disponibilidad para ese pedido. No se registró ninguna reserva."
        resumen = (f"{'Crear reserva' if accion == 'crear' else 'Modificar reserva ' + datos['reserva_id']}: "
                   f"{datos.get('nombre') or anterior.get('nombre')}, {fecha} a las {hora}, {personas} personas")
        if accion == "crear":
            resumen += f", contacto {datos['telefono']}, zona {datos.get('zona') or 'según disponibilidad'}"
            if datos.get("notas"):
                resumen += f", observaciones: {datos['notas']}"
    else:
        r = datos["anterior"]
        resumen = f"Cancelar reserva {r['id']}: {r['nombre']}, {r['fecha']} a las {r['hora']}, {r['personas']} personas"

    codigo = secrets.token_hex(4).upper()
    with _db() as db:
        db.execute("INSERT OR REPLACE INTO propuestas VALUES (?, ?, ?, ?, ?)",
                   (sesion, codigo, accion, json.dumps(datos), time.time() + VIGENCIA_SEGUNDOS))
    texto = f"{resumen}. Todavía no se realizó la operación. Para autorizarla escribe CONFIRMO {codigo}. Válido durante 10 minutos."
    contexto.datos["confirmacion_pendiente"] = texto
    return texto


def confirmar(sesion, texto, servicio):
    """Solo un mensaje completo confirma; el LLM no interpreta ni ejecuta el permiso.

    Retorna None si es texto conversacional. El token es de un uso, ligado a
    sesion, parametros y version de reserva. No se reintenta una escritura incierta.

    Para un comando exacto retorna (texto, datos): rechazos tienen datos={},
    exito incluye reserva y operacion. Comprueba sesion, token y vencimiento,
    consume la propuesta antes de escribir y vuelve a comprobar propiedad y
    version para modificar/cancelar. Crear vincula la reserva nueva a la sesion.
    Convierte ValueError del servicio en rechazo; otros errores se propagan.
    """
    match = re.fullmatch(r"\s*CONFIRMO\s+([0-9A-F]{8})\s*[.!]?\s*", texto, re.I)
    if not match:
        return None
    with _lock:
        with _db() as db:
            db.execute("BEGIN IMMEDIATE")
            fila = db.execute("SELECT codigo, accion, datos, vence FROM propuestas WHERE sesion=?", (sesion,)).fetchone()
            if not fila or not secrets.compare_digest(fila[0], match[1].upper()) or fila[3] < time.time():
                return "La confirmación no es válida o venció. Solicita un nuevo resumen; no se realizó ninguna operación.", {}
            db.execute("DELETE FROM propuestas WHERE sesion=?", (sesion,))
        _, accion, crudo, _ = fila
        datos = json.loads(crudo)
        anterior = datos.pop("anterior", None)
        if accion != "crear":
            actual = servicio.obtener_reserva(datos["reserva_id"])
            if not es_propietario(sesion, datos["reserva_id"]):
                return DENEGADO, {}
            if actual is None or actual.__dict__ != anterior:
                return "La reserva cambió desde el resumen. Solicita uno nuevo antes de confirmar.", {}
        try:
            if accion == "crear":
                r = servicio.crear_reserva(**datos)
                vincular(sesion, r.id)
            elif accion == "modificar":
                r = servicio.modificar_reserva(**datos)
            else:
                r = servicio.cancelar_reserva(**datos)
            if r is None:
                return "No se pudo completar la operación. Solicita revisar la reserva.", {}
        except ValueError:
            return "No se pudo completar la operación: la disponibilidad o los datos cambiaron. Solicita un nuevo resumen.", {}
        estado = {"crear": "confirmada", "modificar": "actualizada", "cancelar": "cancelada"}[accion]
        return (f"Reserva {r.id} {estado}: {r.nombre}, {r.fecha} a las {r.hora}, {r.personas} personas, zona {r.zona}.",
                {"reserva": r.__dict__, "operacion": accion})
