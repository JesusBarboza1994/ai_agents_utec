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
    if not sesion or sesion in {"desconocida", "studio"}:
        raise ValueError("Sesion no identificada")
    with _db() as db:
        db.execute("INSERT INTO propietarios VALUES (?, ?)", (reserva_id, sesion))


def es_propietario(sesion, reserva_id):
    with _db() as db:
        return db.execute("SELECT 1 FROM propietarios WHERE reserva=? AND sesion=?", (reserva_id, sesion)).fetchone() is not None


def reservas_propias(sesion, servicio):
    with _db() as db:
        ids = [r[0] for r in db.execute("SELECT reserva FROM propietarios WHERE sesion=?", (sesion,))]
    return [r for codigo in ids if (r := servicio.obtener_reserva(codigo)) is not None]


def descartar(sesion):
    with _db() as db:
        db.execute("DELETE FROM propuestas WHERE sesion=?", (sesion,))


def proponer(contexto, accion, datos, servicio):
    """Las tools solo preparan. El usuario confirma el resumen generado por codigo."""
    sesion = contexto.sesion_id
    if not sesion or sesion in {"desconocida", "studio"}:
        return "No se puede preparar una operación sin una sesión identificada. Usa el chat."
    datos = dict(datos)
    if accion in {"modificar", "cancelar"}:
        codigo = datos["reserva_id"]
        if not es_propietario(sesion, codigo):
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
