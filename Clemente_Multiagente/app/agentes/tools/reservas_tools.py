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

from . import con_traza

from ...reservas import obtener_servicio as servicio_reservas
from ..memoria import recordar

# Grupos por encima de este tamano no los cierra el agente: van al staff.
LIMITE_GRUPO_AUTONOMO = 10


@tool
@con_traza
def consultar_disponibilidad(
    fecha: str, hora: str, personas: int, runtime: ToolRuntime, zona: str = ""
) -> str:
    """Consulta que mesas hay libres. Usar SIEMPRE antes de afirmar que hay o no hay lugar.

    Args:
        fecha: fecha en formato YYYY-MM-DD.
        hora: turno en formato HH:MM (12:00, 13:00, 14:00, 19:00, 20:00, 21:00 o 22:00).
        personas: numero de comensales.
        zona: opcional, "salon", "terraza" o "barra".
    """
    if personas > LIMITE_GRUPO_AUTONOMO:
        return (
            f"Grupo de {personas} personas: excede lo que se confirma por chat. "
            "Usa escalar_a_staff con el detalle del pedido."
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
    runtime: ToolRuntime, zona: str = "", notas: str = "",
) -> str:
    """Registra la reserva. Llamar SOLO despues de que el cliente confirmo explicitamente
    fecha, hora, numero de personas y su nombre.

    Args:
        nombre: nombre del cliente.
        telefono: telefono de contacto.
        fecha: YYYY-MM-DD.
        hora: HH:MM.
        personas: numero de comensales.
        zona: opcional, zona preferida.
        notas: alergias, ocasion especial u otra indicacion del cliente.
    """
    if personas > LIMITE_GRUPO_AUTONOMO:
        return f"No registrada: {personas} personas requiere coordinacion con el staff."

    try:
        reserva = servicio_reservas().crear_reserva(
            nombre=nombre, telefono=telefono, fecha=fecha, hora=hora,
            personas=personas, zona=zona or "", notas=notas,
        )
    except ValueError as error:
        return f"No se pudo registrar: {error}"

    # Memoria de largo plazo: a partir de aqui el restaurante conoce a este cliente
    # aunque se reinicie el servidor o cambie de conversacion.
    recordar(runtime.context.sesion_id, nombre=nombre, telefono=telefono)
    runtime.context.datos["reserva"] = reserva.__dict__

    return (
        f"Reserva {reserva.id} confirmada: {reserva.nombre}, {reserva.personas} personas, "
        f"{reserva.fecha} {reserva.hora}, zona {reserva.zona} (mesa {reserva.mesa_id})."
    )


@tool
@con_traza
def buscar_mis_reservas(telefono: str, runtime: ToolRuntime) -> str:
    """Lista las reservas asociadas a un telefono. Usar antes de modificar o cancelar."""
    reservas = servicio_reservas().buscar_reservas_de(telefono)
    if not reservas:
        return f"No hay reservas registradas con el telefono {telefono}."

    recordar(runtime.context.sesion_id, telefono=telefono, nombre=reservas[-1].nombre)
    return "; ".join(
        f"{r.id}: {r.fecha} {r.hora}, {r.personas} personas, zona {r.zona}, {r.estado}"
        for r in reservas
    )


@tool
@con_traza
def consultar_reserva_por_codigo(reserva_id: str, runtime: ToolRuntime) -> str:
    """Busca una reserva por su codigo (por ejemplo R-51BA96), cuando el cliente lo da
    en vez del telefono. Usar antes de modificar o cancelar si solo tienes el codigo."""
    reserva = servicio_reservas().obtener_reserva(reserva_id.strip().upper())
    if reserva is None:
        return f"No existe ninguna reserva con el codigo {reserva_id}."
    return (
        f"{reserva.id}: {reserva.nombre}, {reserva.personas} personas, {reserva.fecha} "
        f"{reserva.hora}, zona {reserva.zona} (mesa {reserva.mesa_id}), estado {reserva.estado}."
    )


@tool
@con_traza
def modificar_reserva(
    reserva_id: str, runtime: ToolRuntime, fecha: str = "", hora: str = "", personas: int = 0
) -> str:
    """Cambia fecha, hora o numero de personas de una reserva existente.

    Args:
        reserva_id: codigo de la reserva (por ejemplo R-A1B2C3).
        fecha: nueva fecha YYYY-MM-DD, vacio si no cambia.
        hora: nueva hora HH:MM, vacio si no cambia.
        personas: nuevo numero de personas, 0 si no cambia.
    """
    try:
        reserva = servicio_reservas().modificar_reserva(
            reserva_id.strip().upper(), fecha or None, hora or None, personas or None
        )
    except ValueError as error:
        return f"No se pudo modificar: {error}"

    if reserva is None:
        return f"No existe la reserva {reserva_id}."
    return (
        f"Reserva {reserva.id} actualizada: {reserva.fecha} {reserva.hora}, "
        f"{reserva.personas} personas, zona {reserva.zona} (mesa {reserva.mesa_id})."
    )


@tool
@con_traza
def cancelar_reserva(reserva_id: str, runtime: ToolRuntime) -> str:
    """Cancela una reserva. Requiere que el cliente lo haya pedido explicitamente."""
    reserva = servicio_reservas().cancelar_reserva(reserva_id.strip().upper())
    if reserva is None:
        return f"No existe la reserva {reserva_id}."
    return f"Reserva {reserva.id} del {reserva.fecha} {reserva.hora} cancelada."


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
        "motivo": motivo,
        "detalle": detalle,
    }

    return (
        "Pedido marcado para el equipo del restaurante. Informar al cliente que el caso "
        "quedo anotado, que la mesa TODAVIA no esta confirmada y que una persona del "
        "restaurante lo va a contactar. No menciones ningun codigo: todavia no existe."
    )
