"""
Tools del Agente de Reservas y Capacidad.

Regla del Entregable 01 que estas tools hacen cumplir por construccion: el
agente no puede afirmar disponibilidad sin llamar a `consultar_disponibilidad`,
y no puede registrar nada sin `crear_reserva`, que vuelve a verificar la mesa
antes de escribir (doble verificacion).

El `sesion_id` no es un argumento del modelo: llega por `runtime: ToolRuntime`,
el contexto que `create_agent` inyecta y que el modelo no ve.
"""

from langchain.tools import ToolRuntime, tool

from . import con_traza, limpiar_texto

from ...observabilidad.trazas import registrar
from ...reservas import obtener_servicio as servicio_reservas
from .. import autorizacion
from .. import fecha as reloj

# Grupos por encima de este tamano no los cierra el agente: van al staff.
LIMITE_GRUPO_AUTONOMO = 10


def _rechazo_de_fecha(runtime: ToolRuntime, fecha: str | None, dia_semana: str) -> str | None:
    """Texto de rechazo si el dia de la semana no cae en la fecha o la fecha ya paso; None si esta bien.

    La contradiccion deja `guardrail_fecha` en el contexto y en la traza: el
    servidor no elige entre "viernes" y "el 13", lo pregunta el agente. Una
    fecha con formato invalido no se rechaza aqui: sigue su camino de siempre."""
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
    return None


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
    rechazo = _rechazo_de_fecha(runtime, fecha, dia_semana)
    if rechazo:
        return rechazo

    if personas > LIMITE_GRUPO_AUTONOMO:
        return (
            f"Grupo de {personas} personas: excede lo que se confirma por chat. "
            "Reúne nombre, teléfono, fecha y hora, y usa solicitar_excepcion_grupo."
        )

    opciones = servicio_reservas().consultar_disponibilidad(fecha, hora, personas, zona or None)
    if not opciones:
        return f"Sin disponibilidad para {personas} personas el {fecha} a las {hora}."

    detalle = ", ".join(f"{o.zona} (mesa {o.mesa_id}, hasta {o.capacidad})" for o in opciones[:3])
    return f"Disponible el {fecha} a las {hora} para {personas} personas en: {detalle}."


@tool
@con_traza
def crear_reserva(
    nombre: str, telefono: str, fecha: str, hora: str, personas: int,
    runtime: ToolRuntime, zona: str = "", notas: str = "", dia_semana: str = "",
) -> str:
    """Prepara un resumen de reserva; NO escribe la reserva.
    Usar cuando se conocen los datos. El cliente debe enviar despues CONFIRMO
    con el codigo devuelto; solo el servidor ejecuta esa confirmacion.

    Args:
        nombre: nombre del cliente.
        telefono: telefono de contacto.
        fecha: YYYY-MM-DD.
        hora: HH:MM.
        personas: numero de comensales.
        zona: opcional, zona preferida.
        notas: alergias, ocasion especial u otra indicacion del cliente.
        dia_semana: el dia de la semana que dijo el cliente, si lo dijo; el servidor
            rechaza el resumen si no coincide con la fecha.
    """
    rechazo = _rechazo_de_fecha(runtime, fecha, dia_semana)
    if rechazo:
        return rechazo
    return autorizacion.proponer(runtime.context, "crear", {
        "nombre": limpiar_texto(nombre, 80), "telefono": limpiar_texto(telefono, 20),
        "fecha": fecha, "hora": hora, "personas": personas,
        "zona": limpiar_texto(zona, 20), "notas": limpiar_texto(notas, 300),
    }, servicio_reservas())


@tool
@con_traza
def buscar_mis_reservas(telefono: str, runtime: ToolRuntime) -> str:
    """Lista reservas propias de la sesion cuyo telefono coincide con el recibido.

    Usar antes de modificar o cancelar. Conocer el telefono no concede acceso;
    sin registros autorizados devuelve rechazo y marca guardrail_autorizacion.
    """
    telefono = limpiar_texto(telefono, 20)
    reservas = [r for r in autorizacion.reservas_propias(runtime.context.sesion_id, servicio_reservas())
                if r.telefono == telefono]
    if not reservas:
        runtime.context.datos["guardrail_autorizacion"] = {"estado": "bloqueado"}
        return autorizacion.DENEGADO
    return "; ".join(f"{r.id}: {r.fecha} {r.hora}, {r.personas} personas, zona {r.zona}, {r.estado}" for r in reservas)


@tool
@con_traza
def consultar_reserva_por_codigo(reserva_id: str, runtime: ToolRuntime) -> str:
    """Consulta una reserva propia por codigo, normalizado a mayusculas.

    Usar antes de modificar o cancelar cuando el cliente da el codigo. Verifica
    propiedad de la sesion del runtime antes de leer; un codigo ajeno o inexistente
    devuelve el mismo rechazo y marca guardrail_autorizacion sin revelar datos.
    """
    codigo = limpiar_texto(reserva_id, 20).upper()
    if not autorizacion.es_propietario(runtime.context.sesion_id, codigo):
        runtime.context.datos["guardrail_autorizacion"] = {"estado": "bloqueado"}
        return autorizacion.DENEGADO
    reserva = servicio_reservas().obtener_reserva(codigo)
    if reserva is None:
        runtime.context.datos["guardrail_autorizacion"] = {"estado": "bloqueado"}
        return autorizacion.DENEGADO
    return (f"{reserva.id}: {reserva.nombre}, {reserva.personas} personas, {reserva.fecha} "
            f"{reserva.hora}, zona {reserva.zona}, estado {reserva.estado}.")


@tool
@con_traza
def modificar_reserva(
    reserva_id: str, runtime: ToolRuntime, fecha: str = "", hora: str = "", personas: int = 0,
    dia_semana: str = "",
) -> str:
    """Prepara un cambio de una reserva propia, sin ejecutarlo.
    El servidor exige despues CONFIRMO con el codigo del resumen.

    Args:
        reserva_id: codigo de la reserva (por ejemplo R-A1B2C3).
        fecha: nueva fecha YYYY-MM-DD, vacio si no cambia.
        hora: nueva hora HH:MM, vacio si no cambia.
        personas: nuevo numero de personas, 0 si no cambia.
        dia_semana: el dia de la semana que dijo el cliente para la nueva fecha, si lo dijo.
    """
    rechazo = _rechazo_de_fecha(runtime, fecha or None, dia_semana)
    if rechazo:
        return rechazo
    return autorizacion.proponer(runtime.context, "modificar", {
        "reserva_id": reserva_id.strip().upper(), "fecha": fecha or None,
        "hora": hora or None, "personas": personas or None,
    }, servicio_reservas())


@tool
@con_traza
def cancelar_reserva(reserva_id: str, runtime: ToolRuntime) -> str:
    """Prepara cancelar una reserva propia. No cancela hasta recibir CONFIRMO y su codigo."""
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
    """Solicita al staff revisar un grupo de más de 10 personas.

    Esta herramienta se pausa antes de ejecutarse. Solo una aprobación humana
    permite que el orquestador abra el caso; una denegación no crea ticket.
    Al ejecutarse tras la aprobación vuelve a comprobar la fecha (pasada o con
    un dia de la semana que no coincide) y en ese caso no abre ningun caso.

    Args:
        dia_semana: el dia de la semana que dijo el cliente, si lo dijo.
    """
    if personas <= LIMITE_GRUPO_AUTONOMO:
        return "No requiere excepción: usa el flujo normal de disponibilidad y reserva."
    rechazo = _rechazo_de_fecha(runtime, fecha, dia_semana)
    if rechazo:
        return rechazo
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
