"""Autorizacion: propiedad por sesion y confirmaciones fuera del LLM.

El telefono y los argumentos de tools NO son identidad. Las reservas antiguas
sin vinculacion requieren recuperacion por personal; no se adjudican por codigo.

Donde vive el estado: con `CLEMENTE_BACKEND_AGENTES=local` (o reservas en
JSON) en SQLite del proceso; con Postgres, en las tablas `agentes_propietarios`
y `agentes_propuestas` del mismo pool que usa el gestor de reservas de Marc
(ver `almacen.py`). El token de un uso es atomico en ambos: `BEGIN IMMEDIATE`
en SQLite, `DELETE ... RETURNING` en Postgres.

Contrato de errores con el servicio de reservas (A9): `ValueError` es regla
de negocio; cualquier otra excepcion es infraestructura y se traduce a texto
explicito. Una escritura que falla DESPUES de consumir el token no se
reintenta: se informa como incierta para que la verifique el restaurante.
"""
import json
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from threading import RLock

from ..observabilidad.trazas import registrar
from . import almacen
from . import fecha as reloj
from .servicios import ServicioNoDisponible, intentar

ARCHIVO = almacen.carpeta_datos() / "autorizaciones.sqlite3"
VIGENCIA_SEGUNDOS = 600
_lock = RLock()
DENEGADO = "No puedo acceder a esa reserva desde esta conversación. Solicita al restaurante que verifique tu identidad para recuperarla."
CONFIRMACION_INVALIDA = "La confirmación no es válida o venció. Solicita un nuevo resumen; no se realizó ninguna operación."
NO_DISPONIBLE = (
    "El sistema de reservas no está disponible en este momento. No se preparó ni se realizó "
    "ninguna operación; indica al cliente que lo intente más tarde o que llame al restaurante."
)
ESCRITURA_INCIERTA = (
    "No puedo confirmar si la operación quedó registrada: el sistema de reservas falló al "
    "escribir. No la repitas por tu cuenta; el restaurante debe verificarla con tu nombre y "
    "teléfono antes de volver a intentarlo."
)


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
    ya vinculada produce el error de integridad del backend."""
    if not sesion or sesion in {"desconocida", "studio"}:
        raise ValueError("Sesion no identificada")
    if almacen.es_postgres():
        almacen.pg_vincular(reserva_id, sesion)
        return
    with _db() as db:
        db.execute("INSERT INTO propietarios VALUES (?, ?)", (reserva_id, sesion))


def es_propietario(sesion, reserva_id):
    """Devuelve si el almacen vincula exactamente reserva_id con sesion; no usa el telefono."""
    if almacen.es_postgres():
        return almacen.pg_es_propietario(reserva_id, sesion)
    with _db() as db:
        return db.execute("SELECT 1 FROM propietarios WHERE reserva=? AND sesion=?", (reserva_id, sesion)).fetchone() is not None


def _codigos_propios(sesion) -> list[str]:
    """Codigos de reserva vinculados a la sesion en el backend activo."""
    if almacen.es_postgres():
        return almacen.pg_reservas_de(sesion)
    with _db() as db:
        return [r[0] for r in db.execute("SELECT reserva FROM propietarios WHERE sesion=?", (sesion,))]


def reservas_propias(sesion, servicio):
    """Devuelve las reservas vinculadas a sesion que todavia existen en servicio.

    Incluye sus estados actuales, tambien canceladas; omite codigos inexistentes.
    Si el servicio falla por infraestructura lanza ServicioNoDisponible."""
    reservas = []
    for codigo in _codigos_propios(sesion):
        reserva = intentar(None, "obtener_reserva", servicio.obtener_reserva, codigo)
        if reserva is not None:
            reservas.append(reserva)
    return reservas


def descartar(sesion):
    """Elimina la propuesta pendiente de sesion sin borrar la propiedad de sus reservas."""
    if almacen.es_postgres():
        almacen.pg_descartar_propuesta(sesion)
        return
    with _db() as db:
        db.execute("DELETE FROM propuestas WHERE sesion=?", (sesion,))


def _guardar_propuesta(sesion, codigo, accion, datos) -> None:
    """Deja la unica propuesta pendiente de la sesion con su token y vencimiento."""
    vence = time.time() + VIGENCIA_SEGUNDOS
    if almacen.es_postgres():
        almacen.pg_guardar_propuesta(sesion, codigo, accion, datos, vence)
        return
    with _db() as db:
        db.execute("INSERT OR REPLACE INTO propuestas VALUES (?, ?, ?, ?, ?)",
                   (sesion, codigo, accion, json.dumps(datos), vence))


def _consumir_propuesta(sesion, codigo) -> tuple[str, dict] | None:
    """Consume atomicamente la propuesta de la sesion si el token coincide y no vencio.

    Devuelve (accion, datos) o None. Dos confirmaciones simultaneas del mismo
    token obtienen la fila una sola vez, en ambos backends."""
    if almacen.es_postgres():
        return almacen.pg_consumir_propuesta(sesion, codigo)
    with _lock:
        with _db() as db:
            db.execute("BEGIN IMMEDIATE")
            fila = db.execute("SELECT codigo, accion, datos, vence FROM propuestas WHERE sesion=?", (sesion,)).fetchone()
            if not fila or not secrets.compare_digest(fila[0], codigo) or fila[3] < time.time():
                return None
            db.execute("DELETE FROM propuestas WHERE sesion=?", (sesion,))
    return fila[1], json.loads(fila[2])


def proponer(contexto, accion, datos, servicio):
    """Prepara crear, modificar o cancelar sin escribir una reserva en el servicio.

    contexto aporta la sesion del servidor; datos contiene los parametros
    de la operacion. Comprueba propiedad para modificar/cancelar y captura
    el registro anterior. Para crear/modificar exige fecha no pasada (en
    hora de Lima), sin contradiccion con el dia de la semana declarado en
    `dia_semana`, y de 1 a 10 personas; crear tambien exige contacto y
    disponibilidad. Una contradiccion dia/fecha se registra en la traza y
    en contexto.datos["guardrail_fecha"] y no deja propuesta.

    Persiste una propuesta por sesion con token y vencimiento y guarda
    confirmacion_pendiente en contexto.datos. Devuelve el resumen del
    servidor con CONFIRMO o el motivo de rechazo. Si el servicio falla por
    infraestructura devuelve NO_DISPONIBLE sin dejar propuesta. Una accion
    desconocida produce ValueError; errores del almacen se propagan.
    """
    sesion = contexto.sesion_id
    if not sesion or sesion in {"desconocida", "studio"}:
        return "No se puede preparar una operación sin una sesión identificada. Usa el chat."
    datos = dict(datos)
    # El dia declarado solo sirve para validar: nunca llega al servicio.
    dia_semana = datos.pop("dia_semana", "") or ""
    try:
        if accion in {"modificar", "cancelar"}:
            codigo = datos["reserva_id"]
            if not es_propietario(sesion, codigo):
                contexto.datos["guardrail_autorizacion"] = {"estado": "bloqueado"}
                return DENEGADO
            actual = intentar(contexto, "obtener_reserva", servicio.obtener_reserva, codigo)
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
            contradiccion = reloj.contradiccion_dia(dia_semana, fecha)
            if contradiccion:
                # "El viernes 13" cuando el 13 es sabado: el servidor no elige por
                # el cliente ni deja una propuesta que se pueda confirmar.
                contexto.datos["guardrail_fecha"] = {
                    "estado": "contradiccion", "dia_declarado": dia_semana, "fecha": fecha,
                }
                registrar("guardrail_fecha", sesion, agente="reservas",
                          detalle={"accion": accion, "dia_declarado": dia_semana, "fecha": fecha})
                return contradiccion
            try:
                if reloj.es_pasada(fecha):
                    raise ValueError()
            except (ValueError, TypeError):
                return "Indica una fecha válida que no esté en el pasado."
            if accion == "crear" and (not datos["nombre"].strip() or not datos["telefono"].strip()):
                return "Faltan el nombre y/o el teléfono de contacto."
            if accion == "crear" and not intentar(
                contexto, "consultar_disponibilidad", servicio.consultar_disponibilidad,
                fecha, hora, personas, datos.get("zona") or None,
            ):
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
    except ServicioNoDisponible:
        return NO_DISPONIBLE

    codigo = secrets.token_hex(4).upper()
    _guardar_propuesta(sesion, codigo, accion, datos)
    texto = f"{resumen}. Todavía no se realizó la operación. Para autorizarla escribe CONFIRMO {codigo}. Válido durante 10 minutos."
    contexto.datos["confirmacion_pendiente"] = texto
    return texto


def confirmar(sesion, texto, servicio):
    """Solo un mensaje completo confirma; el LLM no interpreta ni ejecuta el permiso.

    Retorna None si es texto conversacional. El token es de un uso, ligado a
    sesion, parametros y version de reserva.

    Para un comando exacto retorna (texto, datos): rechazos tienen datos={},
    exito incluye reserva y operacion. Consume la propuesta antes de escribir
    y vuelve a comprobar propiedad y version para modificar/cancelar. Crear
    vincula la reserva nueva a la sesion. Convierte ValueError del servicio
    en rechazo; un fallo de lectura devuelve NO_DISPONIBLE; un fallo al
    escribir devuelve ESCRITURA_INCIERTA con datos["operacion_incierta"] y
    NO se reintenta: el token ya se consumio y el restaurante debe verificar.
    """
    match = re.fullmatch(r"\s*CONFIRMO\s+([0-9A-F]{8})\s*[.!]?\s*", texto, re.I)
    if not match:
        return None
    consumida = _consumir_propuesta(sesion, match[1].upper())
    if consumida is None:
        return CONFIRMACION_INVALIDA, {}
    accion, datos = consumida
    anterior = datos.pop("anterior", None)
    try:
        if accion != "crear":
            actual = intentar(None, "obtener_reserva", servicio.obtener_reserva, datos["reserva_id"])
            if not es_propietario(sesion, datos["reserva_id"]):
                return DENEGADO, {}
            if actual is None or actual.__dict__ != anterior:
                return "La reserva cambió desde el resumen. Solicita uno nuevo antes de confirmar.", {}
    except ServicioNoDisponible:
        return NO_DISPONIBLE, {"servicio_reservas": {"estado": "no_disponible", "operacion": "obtener_reserva"}}
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
    except Exception as error:
        registrar("escritura_incierta", sesion, agente="reservas",
                  detalle={"accion": accion, "error": f"{type(error).__name__}: {error}"[:300]})
        return ESCRITURA_INCIERTA, {"operacion_incierta": accion}
    estado = {"crear": "confirmada", "modificar": "actualizada", "cancelar": "cancelada"}[accion]
    return (f"Reserva {r.id} {estado}: {r.nombre}, {r.fecha} a las {r.hora}, {r.personas} personas, zona {r.zona}.",
            {"reserva": r.__dict__, "operacion": accion})
