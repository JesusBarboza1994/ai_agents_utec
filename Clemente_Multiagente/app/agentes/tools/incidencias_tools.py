"""
Tools del Agente de Incidencias y Experiencia.

Lo que NO existe aqui es tan importante como lo que existe: no hay tool para
cerrar una incidencia, ni para otorgar una compensacion, ni para ofrecer una
reserva. Aunque el prompt fallara, el modelo no tiene con que hacerlo. El
agente registra, informa el plazo y deja el caso con el staff.
"""

from langchain.tools import ToolRuntime, tool

from difflib import SequenceMatcher

from . import con_traza, limpiar_texto

from ...incidencias import abiertas_de, obtener_servicio as servicio_incidencias
from ...reservas import obtener_servicio as servicio_reservas
from .. import autorizacion

# Tope de casos abiertos por conversacion en una hora: un reclamo real no necesita mas.
MAX_CASOS_POR_HORA = 3


def _parecida(a: str, b: str) -> bool:
    """True si dos descripciones son casi iguales (mismo reclamo repetido con otras palabras sueltas)."""
    return SequenceMatcher(None, a.lower()[:300], b.lower()[:300]).ratio() >= 0.85


@tool
@con_traza
def registrar_incidencia(
    descripcion: str, runtime: ToolRuntime, tipo: str = "otro", reserva_id: str = "",
) -> str:
    """Registra el reclamo del cliente con estado, responsable y plazo. Llamar una vez que
    se sabe QUE paso y CUANDO; no hace falta tener todos los detalles.

    La sesion procede del runtime del servidor. Si reserva_id no pertenece a
    esa sesion, rechaza el registro. Guarda la incidencia devuelta en contexto;
    la entrega a Trello depende del backend y no se acredita solo con el codigo.

    Args:
        descripcion: que ocurrio, en palabras del cliente, con la fecha si la menciono.
        tipo: "espera", "servicio", "producto", "reserva" u "otro".
        reserva_id: codigo de reserva relacionado, si lo hay.
    """
    reserva_id = limpiar_texto(reserva_id, 20).upper()
    if reserva_id and not autorizacion.es_propietario(runtime.context.sesion_id, reserva_id):
        return autorizacion.DENEGADO
    descripcion = limpiar_texto(descripcion, 1000)
    previas = abiertas_de(runtime.context.sesion_id, horas=1)
    repetida = next((c for c in previas if _parecida(c.descripcion, descripcion)), None)
    if repetida:
        return f"Ese reclamo ya está registrado con el código {repetida.id}. El equipo lo está revisando; no se abrió otro caso."
    if len(previas) >= MAX_CASOS_POR_HORA:
        return ("Ya hay varios casos abiertos de esta conversación en la última hora y el equipo los está revisando. "
                "No se abrió otro caso; si es algo nuevo y urgente, comunícate directamente con el restaurante.")
    incidencia = servicio_incidencias().crear_incidencia(
        sesion_id=runtime.context.sesion_id,
        descripcion=descripcion,
        tipo=limpiar_texto(tipo, 20),
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
    """Consulta el estado de un reclamo de la misma sesion del runtime.

    Normaliza el codigo y devuelve estado, tipo, fecha y plazo. Un caso ajeno
    o inexistente devuelve rechazo sin revelar sus datos; no cambia el estado.
    """
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
    menciona una reserva. Verifica propiedad de la sesion antes de leer por codigo;
    por telefono filtra exclusivamente reservas propias. No revela reservas ajenas
    ni considera el conocimiento del telefono como prueba de identidad."""
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
