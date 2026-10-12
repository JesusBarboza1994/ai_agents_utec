"""Autorizacion local: propiedad por sesion y confirmaciones fuera del LLM.

El telefono y los argumentos de tools NO son identidad. Las reservas antiguas
sin vinculacion requieren recuperacion por personal; no se adjudican por codigo.
Unica excepcion, de solo lectura: en WhatsApp el numero lo verifica el canal, y
deja ver las reservas que tienen ese numero de contacto (reservas_del_numero).
SQLite guarda permisos/propuestas, no reemplaza el gestor de reservas de Miguel.
"""
import hashlib
import json
import re
import secrets
import sqlite3
import time
import unicodedata
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from threading import RLock

from . import casos_abiertos, tope_de_reservas
from . import fecha as reloj
from .contexto import telefono_de
from ..datos import carpeta_de_datos
from ..reservas.validaciones import TURNOS_VALIDOS, ReservaInvalida, validar_cambio_turno, validar_datos_reserva

ARCHIVO = carpeta_de_datos(Path(__file__).parent / "datos") / "autorizaciones.sqlite3"
VIGENCIA_SEGUNDOS = 600
# Un resumen vencido se le avisa al cliente si vencio hace menos que esto: tras un reinicio no se avisa lo de ayer.
VENTANA_AVISO_VENCIDO_SEGUNDOS = 30 * 60
# Conversaciones a las que ya se aviso que su resumen vencio: un CONFIRMO tardio recibe RESUMEN_VENCIDO, no
# "no encuentro un resumen". Vive hasta el siguiente mensaje que no confirma (descartar) o hasta otro resumen.
_vencidas_avisadas: set[str] = set()
# Codigos equivocados que se toleran contra una misma propuesta; al llegar al tope se descarta.
MAX_INTENTOS_CONFIRMO = 5
_intentos_fallidos: dict[str, int] = {}
_lock = RLock()
DENEGADO = ("No puedo acceder a esa reserva desde esta conversación, por tu seguridad. Si necesitas recuperarla, "
            "el restaurante puede verificar tu identidad y ayudarte.")
# No confirma que exista otra reserva ni da su codigo: quien escribe podria no ser su dueno.
RESERVA_REPETIDA_DE_OTRA_CONVERSACION = (
    "No pude registrar esa reserva con esos datos. Si ya habías reservado ese turno desde otra conversación, "
    "el restaurante puede verificar tu identidad y ayudarte a recuperarla; si no, prueba con otro horario y "
    "con gusto lo intento de nuevo."
)
# Un emoji por texto, al final de una frase, como pide la voz de Clemente (VOZ_CLEMENTE). Solo en lo positivo o neutro:
# nunca en un rechazo, un error ni un aviso de seguridad.
EMOJI_DEL_RESUMEN = {"crear": "🍽️", "modificar": "📅", "cancelar": "📅"}
CIERRE_DE_LA_OPERACION = {
    "crear": " ¡Te esperamos! 😄",
    "modificar": " Todo quedó actualizado 👍",
    "cancelar": " Cuando quieras, te ayudo a reservar de nuevo 😊",
}
# Tres motivos distintos por los que un CONFIRMO no se acepta; antes los tres decian "no es valida o vencio".
SIN_RESUMEN_PENDIENTE = (
    "No encuentro un resumen pendiente de confirmar: si escribiste otro mensaje después del resumen, se anuló. "
    "No se hizo ninguna operación; dime qué necesitas y te preparo uno nuevo."
)
CODIGO_NO_COINCIDE = (
    "Ese código no coincide con el último resumen. Para confirmarlo basta con escribir CONFIRMO; "
    "no se hizo ninguna operación."
)
RESUMEN_VENCIDO = (
    "Ese resumen venció (valía 10 minutos). No se hizo ninguna operación; dime qué necesitas y te preparo uno nuevo."
)
DEMASIADOS_INTENTOS = (
    "Hubo demasiados intentos con un código que no coincide, así que cancelé ese resumen por seguridad. "
    "No se hizo ninguna operación; dime qué necesitas y te preparo uno nuevo."
)
# El servidor guarda UNA propuesta por conversacion. Si el modelo prepara dos a la vez (llama las herramientas en
# paralelo), la segunda ya no pisa a la primera en silencio: se rechaza, y el cliente lo lee en el resumen.
OPERACION_YA_PREPARADA = (
    "Ya hay otra operación preparada en este mensaje, esperando la confirmación del cliente. Se prepara una a la vez: "
    "no prepares esta; dile que la haces cuando confirme la primera."
)
AVISO_OPERACION_APLAZADA = (
    "Hago una operación a la vez: te dejo preparada esta y, cuando la confirmes, te ayudo con la otra."
)

# Que cuenta como confirmar: el mensaje ENTERO, sin importar mayusculas, tildes ni signos en los bordes.
# Las FUERTES nombran la accion (confirmo, confirmar): siempre son un intento de confirmar y, sin resumen pendiente,
# se avisa. Las DEBILES son respuestas corrientes de una conversacion ("si"): solo confirman si hay un resumen
# pendiente; sin resumen siguen su camino normal. "ok", "listo", "perfecto" y "gracias" no estan: suelen ser acuse
# de recibo, no una orden de escribir en la reserva. Un mensaje con algo mas ("confirmo pero cambia la hora") no cuenta.
CONFIRMACIONES_FUERTES = frozenset({
    "confirmo", "confirmar", "confirmado", "lo confirmo", "si confirmo", "confirmo la reserva", "confirmo reserva",
    "confirmo todo", "quiero confirmar", "ok confirmo",
})
CONFIRMACIONES_DEBILES = frozenset({"si", "dale", "de acuerdo", "acepto", "adelante", "correcto", "esta bien", "procede"})


def _como_confirmacion(texto):
    """("fuerte" | "debil", codigo | None) si el mensaje entero es una confirmacion; None si no lo es.

    Una confirmacion fuerte puede traer ademas un codigo de 8 caracteres (el de un resumen viejo); si viene, tiene que
    coincidir. No se normaliza con NFKD: las letras de ancho completo o de otro alfabeto no cuentan."""
    if not isinstance(texto, str) or len(texto) > 80:
        return None
    limpio = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").lower()
    limpio = " ".join(re.sub(r"[,;:]", " ", limpio).split())
    limpio = re.sub(r"^[\W_]+|[\W_]+$", "", limpio)      # signos y emojis en los bordes: "¡Confirmo! 👍"
    codigo = None
    con_codigo = re.fullmatch(r"(.+?) ([0-9a-f]{8})", limpio)
    if con_codigo and con_codigo[1] in CONFIRMACIONES_FUERTES:
        limpio, codigo = con_codigo[1], con_codigo[2]
    if limpio in CONFIRMACIONES_FUERTES:
        return "fuerte", codigo
    if limpio in CONFIRMACIONES_DEBILES:
        return "debil", None
    return None


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


def _codigo_de_confirmacion():
    """Sortea el codigo de 8 hex de CONFIRMO, siempre con al menos una letra A-F.

    Un codigo de solo digitos (2,3 % de los sorteos) lo toma por DNI el filtro de
    app/seguridad/pii.py y lo tapa en la respuesta: el cliente no podria confirmar."""
    while True:
        codigo = secrets.token_hex(4).upper()
        if not codigo.isdigit():
            return codigo


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


def numero_verificado(contexto) -> str | None:
    """El numero de WhatsApp desde el que escribe el cliente; None en el webchat o con el id oculto de WhatsApp.

    Es el unico telefono que prueba algo: la sesion whatsapp-<numero> solo la arma el webhook firmado por Twilio (el
    webchat usa web-<uuid> de su cookie firmada). El telefono que el cliente escribe en el chat sigue sin probar nada."""
    if getattr(contexto, "canal", "") != "whatsapp":
        return None
    numero = telefono_de(getattr(contexto, "sesion_id", "") or "") or ""
    return numero if numero.isdigit() and 7 <= len(numero) <= 15 else None


def _formas_del_numero(numero: str) -> set[str]:
    """Como puede estar guardado ese numero de contacto: 51999111222, +51999111222 o, si es de Peru, 999111222."""
    formas = {numero, f"+{numero}"}
    if numero.startswith("51") and len(numero) == 11:
        formas.add(numero[2:])
    return formas


def reservas_del_numero(contexto, servicio):
    """Reservas cuyo contacto es el numero de WhatsApp verificado del cliente, hechas desde cualquier chat; [] si no hay numero.

    Solo para mostrarlas: cambiar o cancelar sigue exigiendo que la reserva sea de esta conversacion (es_propietario)."""
    numero = numero_verificado(contexto)
    if not numero:
        return []
    encontradas = {}
    for forma in _formas_del_numero(numero):
        for reserva in servicio.buscar_reservas_de(forma):
            encontradas[reserva.id] = reserva
    return list(encontradas.values())


def _zona(zona) -> str:
    """La zona como la lee el cliente: se guarda "salon" (es una clave) pero en el texto va salón."""
    return {"salon": "salón"}.get(zona, zona)


def _dia_y_fecha(fecha) -> str:
    """Devuelve el dia y la fecha (sabado 2026-10-10); el dia lo calcula el servidor, para que el cliente vea si coincide con lo que quiso."""
    try:
        return f"{reloj.nombre_dia(date.fromisoformat(fecha))} {fecha}"
    except (TypeError, ValueError):
        return str(fecha)


def descartar(sesion):
    """Elimina la propuesta pendiente de sesion sin borrar la propiedad de sus reservas."""
    _intentos_fallidos.pop(sesion, None)
    _vencidas_avisadas.discard(sesion)
    with _db() as db:
        db.execute("DELETE FROM propuestas WHERE sesion=?", (sesion,))


def retirar_vencidas(ahora=None):
    """Saca las propuestas que vencieron hace poco y devuelve [(sesion, accion)] para avisarle a cada cliente.

    Cada propuesta sale una sola vez, bajo el mismo candado que confirmar: un CONFIRMO que llega a la vez o se
    ejecuta antes (y la consume) o encuentra la propuesta ya retirada y recibe RESUMEN_VENCIDO. Las que vencieron
    hace mas de VENTANA_AVISO_VENCIDO_SEGUNDOS no se tocan: un CONFIRMO tardio sigue recibiendo RESUMEN_VENCIDO."""
    ahora = time.time() if ahora is None else ahora
    with _lock:
        with _db() as db:
            db.execute("BEGIN IMMEDIATE")
            filas = db.execute("SELECT sesion, codigo, accion FROM propuestas WHERE vence <= ? AND vence > ?",
                               (ahora, ahora - VENTANA_AVISO_VENCIDO_SEGUNDOS)).fetchall()
            for sesion, codigo, _ in filas:
                db.execute("DELETE FROM propuestas WHERE sesion=? AND codigo=?", (sesion, codigo))
        for sesion, _, _ in filas:
            _intentos_fallidos.pop(sesion, None)
            _vencidas_avisadas.add(sesion)
    return [(sesion, accion) for sesion, _, accion in filas]


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
    if accion == "crear":
        # Una operacion a la vez: con un pedido al equipo sin atender no se abre otra reserva (casos_abiertos).
        abierto = casos_abiertos.caso_de_atencion_abierto(sesion)
        if abierto:
            texto = casos_abiertos.BLOQUEO_POR_CASO_ABIERTO.format(codigo=abierto)
            contexto.datos["operacion_bloqueada"] = texto
            return texto
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
        try:
            if accion == "crear":
                # Validacion completa (turno + telefono + nombre/notas
                # saneados): la unica fuente de verdad vive en
                # app/reservas/validaciones.py, la misma que corren
                # crear_reserva/modificar_reserva del backend, para que un
                # dato invalido nunca dependa de que esta capa lo repita bien.
                saneado = validar_datos_reserva(
                    nombre=datos.get("nombre", ""), telefono=datos.get("telefono", ""),
                    fecha=fecha, hora=hora, personas=personas,
                    zona=datos.get("zona", ""), notas=datos.get("notas", ""),
                )
                datos.update(saneado)
                fecha, hora, personas = saneado["fecha"], saneado["hora"], saneado["personas"]
            else:
                validar_cambio_turno(fecha=fecha, hora=hora, personas=personas)
        except ReservaInvalida as err:
            return f"No se preparó la operación: {err}"
        # El destino de crear o modificar debe caer en el horario de atencion. La hora solo se
        # revisa si es un turno valido: si no lo es, ya lo rechazo la validacion de arriba.
        fuera = reloj.fuera_de_horario(fecha, hora if hora in TURNOS_VALIDOS else None)
        if fuera:
            return fuera
        if accion == "crear":
            # Tope de reservas activas por conversacion y por telefono, y una sola por turno (tope_de_reservas).
            motivo = tope_de_reservas.motivo_de_rechazo(
                reservas_propias(sesion, servicio), servicio.buscar_reservas_de(datos["telefono"]),
                telefono=datos["telefono"], fecha=fecha, hora=hora, personas=personas, hoy=reloj.hoy().isoformat())
            if motivo:
                contexto.datos["operacion_bloqueada"] = motivo
                return motivo
        if accion == "crear" and not servicio.consultar_disponibilidad(fecha, hora, personas, datos.get("zona") or None):
            return "No hay disponibilidad para ese pedido. No se registró ninguna reserva."
        resumen = (f"{'Esto es lo que voy a reservar' if accion == 'crear' else 'Voy a modificar la reserva ' + datos['reserva_id']}: "
                   f"{datos.get('nombre') or anterior.get('nombre')}, {_dia_y_fecha(fecha)} a las {hora} (hora de Lima), {personas} personas")
        if accion == "crear":
            resumen += f", contacto {datos['telefono']}, zona {_zona(datos.get('zona')) or 'según disponibilidad'}"
            if datos.get("notas"):
                resumen += f", observaciones: {datos['notas']}"
    else:
        r = datos["anterior"]
        resumen = f"Voy a cancelar la reserva {r['id']}: {r['nombre']}, {_dia_y_fecha(r['fecha'])} a las {r['hora']} (hora de Lima), {r['personas']} personas"

    # Huella del pedido, no el pedido: asi un reintento identico se reconoce sin dejar nombre ni telefono en el contexto.
    huella = hashlib.sha256(json.dumps({"accion": accion, **datos}, sort_keys=True, default=str).encode()).hexdigest()[:16]
    # Revisar y guardar van juntos bajo el candado: las herramientas corren en paralelo sobre el mismo contexto.
    with _lock:
        previa = contexto.datos.get("confirmacion_pendiente")
        if previa:
            if contexto.datos.get("huella_de_la_propuesta") == huella:
                return previa            # el mismo pedido otra vez: sigue valiendo el mismo CONFIRMO
            contexto.datos["operacion_aplazada"] = True
            return OPERACION_YA_PREPARADA
        _intentos_fallidos.pop(sesion, None)
        _vencidas_avisadas.discard(sesion)
        codigo = _codigo_de_confirmacion()
        with _db() as db:
            db.execute("INSERT OR REPLACE INTO propuestas VALUES (?, ?, ?, ?, ?)",
                       (sesion, codigo, accion, json.dumps(datos), time.time() + VIGENCIA_SEGUNDOS))
        texto = f"{resumen}. Todavía no está hecho: para confirmarlo, escribe CONFIRMO (vale 10 minutos) {EMOJI_DEL_RESUMEN[accion]}"
        contexto.datos["confirmacion_pendiente"] = texto
        contexto.datos["huella_de_la_propuesta"] = huella
    return texto


def confirmar(sesion, texto, servicio):
    """Solo un mensaje completo confirma; el LLM no interpreta ni ejecuta el permiso.

    Retorna None si es texto conversacional. El token es de un uso, ligado a
    sesion, parametros y version de reserva. No se reintenta una escritura incierta.

    Para un comando exacto retorna (texto, datos): rechazos tienen datos={},
    exito incluye reserva y operacion. Comprueba sesion, token y vencimiento,
    consume la propuesta antes de escribir y vuelve a comprobar propiedad y
    version para modificar/cancelar. Crear vincula la reserva nueva a la sesion; si esa
    reserva ya existia (mismo telefono, dia, hora y personas), avisa a su dueno cual es y a
    cualquier otra sesion no le da el codigo. Convierte ValueError del servicio en rechazo;
    otros errores se propagan.
    """
    confirmacion = _como_confirmacion(texto)
    if confirmacion is None:
        return None
    fuerza, codigo_dado = confirmacion
    with _lock:
        with _db() as db:
            db.execute("BEGIN IMMEDIATE")
            fila = db.execute("SELECT codigo, accion, datos, vence FROM propuestas WHERE sesion=?", (sesion,)).fetchone()
            if fila is None and fuerza == "debil":
                return None            # un "si" corriente sin resumen pendiente es parte de la conversacion
            coincide = bool(fila) and (codigo_dado is None or secrets.compare_digest(fila[0], codigo_dado.upper()))
            if not fila or not coincide or fila[3] < time.time():
                if fila:
                    _intentos_fallidos[sesion] = _intentos_fallidos.get(sesion, 0) + 1
                    if _intentos_fallidos[sesion] >= MAX_INTENTOS_CONFIRMO:
                        db.execute("DELETE FROM propuestas WHERE sesion=?", (sesion,))
                        _intentos_fallidos.pop(sesion, None)
                        return DEMASIADOS_INTENTOS, {}
                if not fila:
                    if sesion in _vencidas_avisadas:
                        # Ya se le aviso que vencio: "no encuentro un resumen" lo confundiria.
                        _vencidas_avisadas.discard(sesion)
                        return RESUMEN_VENCIDO, {}
                    return SIN_RESUMEN_PENDIENTE, {}
                return (CODIGO_NO_COINCIDE if not coincide else RESUMEN_VENCIDO), {}
            db.execute("DELETE FROM propuestas WHERE sesion=?", (sesion,))
            _intentos_fallidos.pop(sesion, None)
        _, accion, crudo, _ = fila
        datos = json.loads(crudo)
        anterior = datos.pop("anterior", None)
        if accion != "crear":
            actual = servicio.obtener_reserva(datos["reserva_id"])
            if not es_propietario(sesion, datos["reserva_id"]):
                return DENEGADO, {}
            if actual is None or actual.__dict__ != anterior:
                return "La reserva cambió desde que te mostré el resumen, así que no la toqué. Pídeme uno nuevo y lo confirmamos.", {}
        try:
            if accion == "crear":
                r = servicio.crear_reserva(**datos)
                try:
                    vincular(sesion, r.id)
                except sqlite3.IntegrityError:
                    # El servicio no creo otra: devolvio una reserva que ya existia (mismo telefono, dia, hora y
                    # personas) y esa ya tiene dueno. A quien la hizo se le dice cual es; a otra conversacion no.
                    if es_propietario(sesion, r.id):
                        return (f"Ya tenías esta reserva, así que no creé otra: {r.id}, {r.nombre}, {r.fecha} a las {r.hora} "
                                f"(hora de Lima), {r.personas} personas, zona {_zona(r.zona)}.",
                                {"reserva": r.__dict__, "operacion": "ya_existia"})
                    return RESERVA_REPETIDA_DE_OTRA_CONVERSACION, {}
            elif accion == "modificar":
                r = servicio.modificar_reserva(**datos)
            else:
                r = servicio.cancelar_reserva(**datos)
            if r is None:
                return "No pude completar la operación. Pídeme revisar la reserva y lo intentamos de nuevo.", {}
        except ReservaInvalida as err:
            return f"No pude completar la operación: {err}", {}
        except ValueError:
            return "No pude completar la operación porque la disponibilidad o los datos cambiaron. Pídeme un nuevo resumen y lo vemos.", {}
        estado = {"crear": "confirmada", "modificar": "actualizada", "cancelar": "cancelada"}[accion]
        return (f"Listo, tu reserva {r.id} quedó {estado}: {r.nombre}, {r.fecha} a las {r.hora} (hora de Lima), "
                f"{r.personas} personas, zona {_zona(r.zona)}.{CIERRE_DE_LA_OPERACION[accion]}",
                {"reserva": r.__dict__, "operacion": accion})
