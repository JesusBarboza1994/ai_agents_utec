"""
Tools del Agente de Reservas y Capacidad.

Regla del Entregable 01 que estas tools hacen cumplir por construccion: el
agente no puede afirmar disponibilidad sin llamar a `consultar_disponibilidad`,
y no puede registrar nada sin `crear_reserva`, que vuelve a verificar la mesa
antes de escribir (doble verificacion).

El `sesion_id` no es un argumento del modelo: llega por `runtime: ToolRuntime`,
el contexto que `create_agent` inyecta y que el modelo no ve.
"""

import json
import re

from langchain.tools import ToolRuntime, tool

from . import con_traza, limpiar_texto

from ...observabilidad.trazas import registrar
from ...reservas import obtener_servicio as servicio_reservas
from ...reservas.servicio_json import ARCHIVO_MESAS
from ...reservas.validaciones import (
    TELEFONO_RE, TURNOS_VALIDOS, ReservaInvalida, validar_cambio_turno, validar_nombre,
)
from .. import autorizacion
from .. import fecha as reloj
from ..contexto import ContextoConversacion, telefono_de

def _capacidad_de_la_mesa_mas_grande(por_defecto: int = 10) -> int:
    """Personas que caben en la mesa mas grande del mapa de la operacion (mesas.json); `por_defecto` si no se puede leer."""
    try:
        mesas = json.loads(ARCHIVO_MESAS.read_text(encoding="utf-8"))["mesas"]
        return max(int(mesa["capacidad"]) for mesa in mesas)
    except (OSError, ValueError, KeyError):
        return por_defecto


# Grupos por encima de este tamano no los cierra el agente: van al staff. Son los que ninguna mesa
# recibe: con la mesa mas grande en 8, pedir para 9 o 10 daba "no hay disponibilidad" en vez de pasar
# al equipo, que si puede juntar mesas. Nunca pasa de 10, el maximo que acepta la validacion.
LIMITE_GRUPO_AUTONOMO = min(10, _capacidad_de_la_mesa_mas_grande())
MENSAJE_GRUPO_GRANDE = (
    "Grupo de {personas} personas: excede lo que se confirma por chat. "
    "Reúne nombre, teléfono, fecha y hora, y usa solicitar_excepcion_grupo."
)


def _normalizar_telefono(texto: str) -> str:
    """Quita espacios, guiones, puntos y parentesis: "999 111-222" queda "999111222", como lo valida el servicio."""
    return re.sub(r"[\s().-]", "", limpiar_texto(texto, 30))


def _telefono_conocido(contexto: ContextoConversacion) -> str:
    """Telefono que el sistema ya tiene del cliente, para no pedirselo de nuevo; "" si no hay ninguno.

    Orden: el de contacto que el cliente dio en el chat, el que autentico el canal
    (columna `phone`) y el que trae la sesion de WhatsApp. Solo cuenta lo que tiene
    forma de telefono: un id oculto de WhatsApp (`PE.2227...`) no lo es."""
    cliente = contexto.cliente or {}
    for candidato in (cliente.get("telefono_contacto"), cliente.get("phone"), telefono_de(contexto.sesion_id)):
        if candidato and TELEFONO_RE.match(str(candidato)):
            return str(candidato)
    return ""


def _rechazo_de_fecha(
    runtime: ToolRuntime, fecha: str | None, dia_semana: str, hora: str | None = None,
) -> str | None:
    """Texto de rechazo si el dia no cae en la fecha, la fecha ya paso o cae fuera de horario; None si esta bien.

    El orden importa y conserva los mensajes de siempre: contradiccion, fecha pasada y
    recien despues el horario de atencion. La hora solo se compara con el horario si es
    un turno valido; si no lo es, la reporta la validacion de turno con su mensaje.
    La contradiccion deja `guardrail_fecha` en el contexto y en la traza: el servidor
    no elige entre "viernes" y "el 13", lo pregunta el agente. Una fecha con formato
    invalido no se rechaza aqui: sigue su camino de siempre."""
    if not fecha:
        return None
    contradiccion = reloj.contradiccion_dia(dia_semana, fecha)
    if contradiccion:
        runtime.context.datos["guardrail_fecha"] = {
            "estado": "contradiccion", "dia_declarado": dia_semana, "fecha": fecha,
        }
        registrar("guardrail_fecha", runtime.context.sesion_id, agente="reservas",
                  detalle={"dia_declarado": dia_semana, "fecha": fecha})
        return contradiccion
    try:
        if reloj.es_pasada(fecha):
            return "Indica una fecha válida que no esté en el pasado."
    except ValueError:
        pass
    fuera = reloj.fuera_de_horario(fecha, hora if hora in TURNOS_VALIDOS else None)
    if fuera:
        registrar("guardrail_horario", runtime.context.sesion_id, agente="reservas",
                  detalle={"fecha": fecha, "hora": hora})
    return fuera


@tool
@con_traza
def consultar_disponibilidad(
    fecha: str, hora: str, personas: int, runtime: ToolRuntime, zona: str = "",
    dia_semana: str = "",
) -> str:
    """Consulta que mesas hay libres. Usar SIEMPRE antes de afirmar que hay o no hay lugar.

    Args:
        fecha: fecha en formato YYYY-MM-DD.
        hora: turno en formato HH:MM (12:00, 13:00, 14:00, 19:00, 20:00, 21:00 o 22:00).
        personas: numero de comensales.
        zona: opcional, "salon", "terraza" o "barra".
        dia_semana: el dia de la semana que dijo el cliente ("viernes"), si lo dijo.
            El servidor comprueba que coincida con la fecha antes de consultar.
    """
    rechazo = _rechazo_de_fecha(runtime, fecha, dia_semana, hora)
    if rechazo:
        return rechazo

    if personas > LIMITE_GRUPO_AUTONOMO:
        return MENSAJE_GRUPO_GRANDE.format(personas=personas)

    # Las mismas reglas que crear_reserva: sin esto se afirmaba "hay lugar" para una hora que ya
    # paso hoy, para una fecha a mas de 30 dias o para un turno que el restaurante no tiene.
    try:
        validar_cambio_turno(fecha=fecha, hora=hora, personas=personas)
    except ReservaInvalida as error:
        return str(error)

    opciones = servicio_reservas().consultar_disponibilidad(fecha, hora, personas, zona or None)
    if not opciones:
        return f"Sin disponibilidad para {personas} personas el {fecha} a las {hora}."

    detalle = ", ".join(f"{o.zona} (mesa {o.mesa_id}, hasta {o.capacidad})" for o in opciones[:3])
    return f"Disponible el {fecha} a las {hora} para {personas} personas en: {detalle}."


def _reserva_repetida(sesion_id: str, telefono: str, fecha: str, hora: str, personas: int) -> str | None:
    """Si esta misma conversacion ya tiene una reserva activa con ese telefono, dia, hora y personas,
    devuelve el texto para el cliente; crear_reserva no prepara otro resumen.

    Antes se preparaba el resumen igual y este aviso iba delante, pero el cierre solo le manda al cliente
    el resumen del servidor: el aviso no le llegaba y parecia una reserva nueva (prueba por WhatsApp del
    12-oct). Solo avisa a su dueno: de otra conversacion no muestra nada aqui, y al confirmar le sigue
    diciendo que no se puede (autorizacion.confirmar)."""
    for reserva in servicio_reservas().buscar_reservas_de(telefono):
        if reserva.estado == "cancelada" or (reserva.fecha, reserva.hora, reserva.personas) != (fecha, hora, personas):
            continue
        if autorizacion.es_propietario(sesion_id, reserva.id):
            return (f"Ya tienes una reserva con estos datos: {reserva.id}, {reserva.nombre}, {reserva.fecha} a las "
                    f"{reserva.hora} (hora de Lima), {reserva.personas} personas, zona "
                    f"{autorizacion._zona(reserva.zona)}. No preparé otra; si quieres cambiar algo, dime qué.")
    return None


@tool
@con_traza
def crear_reserva(
    nombre: str, telefono: str, fecha: str, hora: str, personas: int,
    runtime: ToolRuntime, zona: str = "", notas: str = "", dia_semana: str = "",
) -> str:
    """Prepara un resumen de reserva; NO escribe la reserva.
    Usar cuando se conocen los datos. El cliente debe responder despues CONFIRMO;
    solo el servidor ejecuta esa confirmacion.

    Args:
        nombre: nombre del cliente.
        telefono: telefono de contacto. Si la ficha del cliente ya trae uno, usalo tal cual;
            si no tiene ninguno, deja vacio y la herramienta te dira que se lo pidas. Nunca
            inventes un numero ni pases un marcador como [REDACTED_TELEFONO].
        fecha: YYYY-MM-DD.
        hora: HH:MM.
        personas: numero de comensales.
        zona: opcional, zona preferida.
        notas: alergias, ocasion especial u otra indicacion del cliente.
        dia_semana: el dia de la semana que dijo el cliente, si lo dijo; el servidor
            rechaza el resumen si no coincide con la fecha.
    """
    rechazo = _rechazo_de_fecha(runtime, fecha, dia_semana, hora)
    if rechazo:
        return rechazo
    if personas > LIMITE_GRUPO_AUTONOMO:
        return MENSAJE_GRUPO_GRANDE.format(personas=personas)
    try:
        validar_nombre(nombre)
    except ReservaInvalida as error:
        return str(error)
    telefono = _normalizar_telefono(telefono)
    if not any(c.isdigit() for c in telefono):
        # El modelo no trajo un numero (lo pierde entre turnos: el historial lo guarda tapado).
        telefono = _telefono_conocido(runtime.context)
        if not telefono:
            return ("Falta el telefono de contacto. Pidele al cliente un numero para la reserva y "
                    "prepara la reserva cuando lo tengas; no la prepares con un dato inventado.")
    repetida = _reserva_repetida(runtime.context.sesion_id, telefono, fecha, hora, personas)
    if repetida:
        # Lo escribe el servidor (el cierre lo manda tal cual), como los demas bloqueos de una operacion.
        runtime.context.datos["operacion_bloqueada"] = repetida
        return repetida
    return autorizacion.proponer(runtime.context, "crear", {
        "nombre": limpiar_texto(nombre, 80), "telefono": telefono,
        "fecha": fecha, "hora": hora, "personas": personas,
        "zona": limpiar_texto(zona, 20), "notas": limpiar_texto(notas, 300),
    }, servicio_reservas())


# Un chat sin reservas no es un acceso denegado: antes respondia lo mismo que ante una reserva ajena ("por tu
# seguridad...") y el cliente creia que lo habian bloqueado. Decirle que este chat no tiene ninguna no revela nada.
# El cliente usa solo WhatsApp (el webchat es de control interno): el texto no lo manda a la web.
SIN_RESERVAS_EN_ESTE_CHAT = (
    "No hay reservas hechas desde este chat. Díselo así, sin hablar de seguridad: si reservó desde otro número de "
    "WhatsApp, la ve escribiendo desde ese número; si ya no tiene ese celular, con el código R- de la reserva, el "
    "nombre y el teléfono con los que reservó se la puedes mostrar. Ofrécele también preparar una nueva."
)


# Va junto a cada reserva que se ve por el numero de WhatsApp pero se hizo desde otro chat.
SOLO_PARA_VER = " (hecha desde otro chat con este número: se puede ver, no cambiar ni cancelar desde aquí)"

# Quien perdio el celular con el que reservo escribe desde otro numero: con el codigo, el nombre y el telefono de la
# reserva la puede ver (autorizacion.verificar_con_datos). Los textos son para el modelo; ninguno confirma ni niega
# que el codigo exista, y ninguno dice cual de los datos fallo.
PEDIR_DATOS_PARA_VERIFICAR = (
    "Esa reserva no es de este chat y no se puede mostrar sin verificar. No confirmes ni niegues que exista. Si el "
    "cliente dice que es suya y la hizo desde otro número (por ejemplo, perdió ese celular), pídele en un mensaje el "
    "nombre y el teléfono con los que reservó, y vuelve a consultar el código con nombre y telefono."
)
VERIFICADA_CON_DATOS = (
    " (verificada con el nombre y el teléfono de la reserva: se puede ver, no cambiar ni cancelar desde aquí; para "
    "cambiarla o cancelarla, ofrécele dejar el pedido al equipo con escalar_a_staff)"
)
DATOS_NO_COINCIDEN = (
    "Los datos no coinciden con esa reserva. No digas cuál dato falló ni si el código existe: pídele que revise el "
    "código, el nombre y el teléfono con los que reservó, u ofrécele dejar el pedido al equipo con escalar_a_staff."
)
VERIFICACION_BLOQUEADA = (
    "Hubo demasiados intentos con datos que no coinciden, así que por seguridad esa reserva no se verifica más por "
    "este chat. Ofrécele dejar el pedido al equipo con escalar_a_staff: una persona del restaurante verificará su "
    "identidad y lo ayudará."
)


def _linea_de_reserva(r, nota: str = "") -> str:
    """Una reserva en una linea para el modelo: codigo, turno, personas, zona y estado."""
    return f"{r.id}: {r.fecha} {r.hora}, {r.personas} personas, zona {r.zona}, {r.estado}{nota}"


def _detalle_de_reserva(r, nota: str = "") -> str:
    """Una reserva con el nombre, como la devuelve la consulta por codigo."""
    return f"{r.id}: {r.nombre}, {r.personas} personas, {r.fecha} {r.hora}, zona {r.zona}, estado {r.estado}.{nota}"


@tool
@con_traza
def buscar_mis_reservas(runtime: ToolRuntime, telefono: str = "") -> str:
    """Lista las reservas de esta conversacion; no hace falta pedirle el telefono al cliente.

    Usar cuando el cliente pregunta que reservas tiene y antes de modificar o cancelar.
    La sesion es lo que autoriza: el telefono no concede acceso, solo acota si coincide con
    alguna. En WhatsApp se suman las hechas desde otro chat con el numero verificado del
    cliente, marcadas como solo para ver. Sin ninguna lo dice, sin marcarlo como acceso denegado.

    Args:
        telefono: opcional; si el cliente lo dio, se listan primero las hechas con ese numero.
    """
    telefono = limpiar_texto(telefono, 20)
    servicio = servicio_reservas()
    propias = autorizacion.reservas_propias(runtime.context.sesion_id, servicio)
    ids_propias = {r.id for r in propias}
    del_numero = [r for r in autorizacion.reservas_del_numero(runtime.context, servicio) if r.id not in ids_propias]
    if not propias and not del_numero:
        return SIN_RESERVAS_EN_ESTE_CHAT
    coinciden = [r for r in propias if telefono and r.telefono == telefono]
    lineas = [_linea_de_reserva(r) for r in coinciden or propias]
    lineas += [_linea_de_reserva(r, SOLO_PARA_VER) for r in del_numero]
    return "; ".join(lineas)


@tool
@con_traza
def consultar_reserva_por_codigo(
    reserva_id: str, runtime: ToolRuntime, nombre: str = "", telefono: str = "",
) -> str:
    """Consulta una reserva por codigo, normalizado a mayusculas.

    Usar antes de modificar o cancelar cuando el cliente da el codigo, y cuando pregunta por una
    reserva que hizo desde otro numero (por ejemplo, perdio ese celular). Una reserva de esta
    conversacion se ve directo; en WhatsApp tambien la que tiene el numero verificado del cliente.
    Cualquier otra solo se ve si el cliente da el nombre y el telefono con los que reservo, y solo
    para verla. Un codigo ajeno o inexistente responde lo mismo, sin revelar datos, y marca
    guardrail_autorizacion.

    Args:
        reserva_id: codigo de la reserva (por ejemplo R-A1B2C3).
        nombre: nombre con el que se hizo la reserva; solo para verificar una de otro numero.
        telefono: telefono de contacto de la reserva; solo para verificar una de otro numero.
    """
    codigo = limpiar_texto(reserva_id, 20).upper()
    contexto = runtime.context
    servicio = servicio_reservas()
    if autorizacion.es_propietario(contexto.sesion_id, codigo):
        reserva = servicio.obtener_reserva(codigo)
        if reserva is not None:
            return _detalle_de_reserva(reserva)
    else:
        del_numero = next((r for r in autorizacion.reservas_del_numero(contexto, servicio) if r.id == codigo), None)
        if del_numero is not None:
            return _detalle_de_reserva(del_numero, SOLO_PARA_VER)
    nombre, telefono = limpiar_texto(nombre, 80), _normalizar_telefono(telefono)
    if not nombre.strip() or not any(c.isdigit() for c in telefono):
        contexto.datos["guardrail_autorizacion"] = {"estado": "bloqueado"}
        return PEDIR_DATOS_PARA_VERIFICAR
    resultado, reserva = autorizacion.verificar_con_datos(contexto.sesion_id, codigo, nombre, telefono, servicio)
    registrar("verificacion_por_datos", contexto.sesion_id, agente="reservas", detalle={"resultado": resultado})
    if resultado == "ok":
        return _detalle_de_reserva(reserva, VERIFICADA_CON_DATOS)
    contexto.datos["guardrail_autorizacion"] = {"estado": "bloqueado"}
    return VERIFICACION_BLOQUEADA if resultado == "bloqueada" else DATOS_NO_COINCIDEN


@tool
@con_traza
def modificar_reserva(
    reserva_id: str, runtime: ToolRuntime, fecha: str = "", hora: str = "", personas: int = 0,
    dia_semana: str = "",
) -> str:
    """Prepara un cambio de una reserva propia, sin ejecutarlo.
    El servidor exige despues que el cliente escriba CONFIRMO.

    Args:
        reserva_id: codigo de la reserva (por ejemplo R-A1B2C3).
        fecha: nueva fecha YYYY-MM-DD, vacio si no cambia.
        hora: nueva hora HH:MM, vacio si no cambia.
        personas: nuevo numero de personas, 0 si no cambia.
        dia_semana: el dia de la semana que dijo el cliente para la nueva fecha, si lo dijo.
    """
    rechazo = _rechazo_de_fecha(runtime, fecha or None, dia_semana, hora or None)
    if rechazo:
        return rechazo
    return autorizacion.proponer(runtime.context, "modificar", {
        "reserva_id": reserva_id.strip().upper(), "fecha": fecha or None,
        "hora": hora or None, "personas": personas or None,
    }, servicio_reservas())


@tool
@con_traza
def cancelar_reserva(reserva_id: str, runtime: ToolRuntime) -> str:
    """Prepara cancelar una reserva propia. No cancela hasta que el cliente escriba CONFIRMO."""
    return autorizacion.proponer(runtime.context, "cancelar", {
        "reserva_id": reserva_id.strip().upper(),
    }, servicio_reservas())


@tool
@con_traza
def escalar_a_staff(motivo: str, detalle: str, runtime: ToolRuntime) -> str:
    """Deja el caso armado para una persona del restaurante. Usar con grupos grandes,
    conflictos de asignacion o cuando el cliente insiste en algo que el agente no puede resolver.

    Args:
        motivo: resumen corto de por que se escala.
        detalle: todo el contexto que el staff necesita para continuar.
    """
    # ESTA TOOL YA NO CREA EL TICKET. Solo levanta la mano.
    #
    # Boris, asesoria del 2026-09-07 [12:39]: "cuando se escala a humano, el que
    # lo hace es el orquestador de nuevo. Cada uno de los agentes se la devuelve
    # al orquestador... el que administra la comunicacion es el orquestador,
    # porque si no, como persiste en el log. Al final, el unico punto de salida".
    #
    # El argumento no es de estilo, es de auditoria: si cada agente pudiera abrir
    # un ticket por su cuenta, habria tantos puntos de escalamiento como agentes
    # y ninguno con la conversacion completa. El ticket lo abre `grafo.py` en el
    # nodo de cierre, con todo lo que paso en el turno.
    runtime.context.escalado = True
    runtime.context.datos["escalamiento"] = {
        "origen": "reservas",
        "motivo": limpiar_texto(motivo, 200),
        "detalle": limpiar_texto(detalle, 1000),
    }

    return (
        "Pedido marcado para el equipo del restaurante. Informar al cliente que el caso "
        "quedo anotado, que la mesa TODAVIA no esta confirmada y que una persona del "
        "restaurante lo va a contactar. No menciones ningun codigo: todavia no existe."
    )


@tool
@con_traza
def solicitar_excepcion_grupo(
    nombre: str, telefono: str, fecha: str, hora: str, personas: int,
    runtime: ToolRuntime, zona: str = "", notas: str = "", dia_semana: str = "",
) -> str:
    """Solicita al staff revisar un grupo que no cabe en una sola mesa (más personas que la mesa más grande).

    Esta herramienta se pausa antes de ejecutarse. Solo una aprobación humana
    permite que el orquestador abra el caso; una denegación no crea ticket.
    Al ejecutarse tras la aprobación vuelve a comprobar la fecha (pasada o con
    un dia de la semana que no coincide) y en ese caso no abre ningun caso.

    Args:
        dia_semana: el dia de la semana que dijo el cliente, si lo dijo.
    """
    if personas <= LIMITE_GRUPO_AUTONOMO:
        return "No requiere excepción: usa el flujo normal de disponibilidad y reserva."
    rechazo = _rechazo_de_fecha(runtime, fecha, dia_semana, hora)
    if rechazo:
        return rechazo
    try:
        validar_nombre(nombre)
    except ReservaInvalida as error:
        return str(error)
    nombre, telefono = limpiar_texto(nombre, 80), limpiar_texto(telefono, 20)
    zona, notas = limpiar_texto(zona, 20), limpiar_texto(notas, 300)

    runtime.context.escalado = True
    runtime.context.datos["escalamiento"] = {
        "origen": "reservas_hitl",
        "motivo": f"excepción aprobada para grupo de {personas} personas",
        "detalle": (
            f"Nombre: {nombre}; teléfono: {telefono}; fecha: {fecha}; hora: {hora}; "
            f"zona: {zona or 'sin preferencia'}; notas: {notas or 'sin notas'}"
        ),
    }
    runtime.context.datos["revision_humana"] = {
        "estado": "aprobada", "flujo": "reservas", "decision": "approve",
    }
    return (
        "El equipo aprobó tramitar la excepción. La mesa aún no está confirmada; "
        "el orquestador debe registrar el caso y comunicar el código real."
    )
