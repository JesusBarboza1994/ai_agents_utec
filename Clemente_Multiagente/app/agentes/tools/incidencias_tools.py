"""
Tools del Agente de Incidencias y Experiencia.

Lo que NO existe aqui es tan importante como lo que existe: no hay tool para
cerrar una incidencia, ni para otorgar una compensacion, ni para ofrecer una
reserva. Aunque el prompt fallara, el modelo no tiene con que hacerlo. El
agente registra, informa el plazo y deja el caso con el staff.
"""

from langchain.tools import ToolRuntime, tool

from . import con_traza

from ...incidencias import obtener_servicio as servicio_incidencias
from ...reservas import obtener_servicio as servicio_reservas
from .. import autorizacion


@tool
@con_traza
def registrar_incidencia(
    descripcion: str, runtime: ToolRuntime, tipo: str = "otro", reserva_id: str = "",
) -> str:
    """Registra el reclamo del cliente con estado, responsable y plazo. Llamar una vez que
    se sabe QUE paso y CUANDO; no hace falta tener todos los detalles.

    Args:
        descripcion: que ocurrio, en palabras del cliente, con la fecha si la menciono.
        tipo: "espera", "servicio", "producto", "reserva" u "otro".
        reserva_id: codigo de reserva relacionado, si lo hay.
    """
    if reserva_id and not autorizacion.es_propietario(runtime.context.sesion_id, reserva_id.strip().upper()):
        return autorizacion.DENEGADO
    incidencia = servicio_incidencias().crear_incidencia(
        sesion_id=runtime.context.sesion_id,
        descripcion=descripcion,
        tipo=tipo,
        reserva_id=reserva_id or None,
    )
    runtime.context.datos["incidencia"] = incidencia.__dict__

    return (
        f"Incidencia {incidencia.id} registrada ({incidencia.tipo}), "
        f"asignada a {incidencia.responsable} con plazo de {incidencia.plazo_horas} horas."
    )


@tool
@con_traza
def consultar_incidencia(incidencia_id: str, runtime: ToolRuntime) -> str:
    """Consulta el estado de una incidencia ya registrada, para responder al cliente
    que pregunta por un reclamo anterior."""
    for incidencia in servicio_incidencias().listar_incidencias():
        if incidencia.id == incidencia_id.strip().upper() and incidencia.sesion_id == runtime.context.sesion_id:
            return (
                f"{incidencia.id}: estado {incidencia.estado}, tipo {incidencia.tipo}, "
                f"creada el {incidencia.creada}, plazo {incidencia.plazo_horas} horas."
            )
    return "No puedo acceder a ese caso desde esta conversación."


@tool
@con_traza
def verificar_reserva_del_reclamo(telefono_o_codigo: str, runtime: ToolRuntime) -> str:
    """Comprueba si el cliente tenia reserva, para no discutir con el sobre lo que dice
    que le paso. Acepta el telefono o el codigo de la reserva. Usar cuando el reclamo
    menciona una reserva."""
    dato = telefono_o_codigo.strip()

    if dato.upper().startswith("R-"):
        if not autorizacion.es_propietario(runtime.context.sesion_id, dato.upper()):
            return autorizacion.DENEGADO
        reserva = servicio_reservas().obtener_reserva(dato.upper())
        if reserva is None:
            return f"No existe ninguna reserva con el codigo {dato}."
        return (
            f"{reserva.id}: {reserva.nombre}, {reserva.fecha} {reserva.hora}, "
            f"{reserva.personas} personas, zona {reserva.zona}, estado {reserva.estado}."
        )

    reservas = [r for r in autorizacion.reservas_propias(runtime.context.sesion_id, servicio_reservas()) if r.telefono == dato]
    if not reservas:
        return autorizacion.DENEGADO

    return "; ".join(f"{r.id}: {r.fecha} {r.hora}, {r.estado}" for r in reservas)
