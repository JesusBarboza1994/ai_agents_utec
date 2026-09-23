"""
Servidor MCP de tickets de Clemente -- Sesion 16 (APIs y MCP).

MCP (*Model Context Protocol*) es el protocolo abierto que permite que un agente
use herramientas que viven **fuera** de su proceso, descubriendolas en tiempo de
ejecucion en vez de tenerlas escritas adentro.

Por que existe este servidor
-----------------------------
Boris, asesoria del 2026-09-07 [05:09]: *"Trello creo que tiene MCP server.
Primero puedes crear el ticket... hasta el mismo agente puede darle seguimiento,
porque tiene el MCP server de Trello"*.

Y el equipo, reconociendo el punto [06:29]: *"nosotros lo estabamos pensando desde
el punto de vista de desarrollarlo uno, pero lo que estas diciendo es basicamente
conectarnos a lo que ya existe"*.

Lo que hay del otro lado de este servidor **es Trello de verdad** -- las tarjetas
que el staff mueve en su tablero. Este proceso solo pone el protocolo delante.

Y ese "delante" es justamente lo que gana el proyecto:

    EL SERVIDOR MCP ES EL LIMITE DE PERMISOS.

Expone cuatro herramientas: crear un ticket, consultarlo, listarlos y dejarle un
comentario. **No expone ninguna para cerrar un ticket, moverlo de lista, borrarlo
ni otorgar una compensacion.** No es que el agente tenga prohibido usarlas: es que
no existen del otro lado del protocolo. Aunque el prompt fallara por completo, y
aunque alguien lograra que el modelo pidiera cerrar un caso, no hay nada que
llamar. Es el mismo principio de "el limite es que tools existen" que ya usamos
dentro del proceso, ahora reforzado por una frontera de proceso.

El cierre de una incidencia lo hace **una persona**, moviendo la tarjeta a
"Resuelto" en su tablero. Eso es lo que exige el Entregable 01 y es lo que este
servidor hace estructuralmente imposible de saltarse.

Como se usa
-----------
Dos transportes, para dos usos distintos:

    # 1. Servidor HTTP de verdad, para la demostracion y para que lo vea el jurado
    python -m app.incidencias.mcp_trello --http
    #    queda escuchando en http://localhost:8100/mcp

    # 2. En memoria, sin levantar ningun puerto: es como corre la evaluacion,
    #    el red team y las pruebas. `fastmcp.Client` acepta el objeto servidor.
    from app.incidencias.mcp_trello import mcp
    async with Client(mcp) as cliente: ...

El transporte cambia; las herramientas y el limite de permisos son los mismos.
"""

import logging
import os
import sys

from fastmcp import FastMCP

from ..contratos import Incidencia

log = logging.getLogger("clemente.mcp")

PUERTO_POR_DEFECTO = int(os.getenv("TRELLO_MCP_PUERTO", "8100"))

mcp = FastMCP("Clemente · tickets de incidencias")


def _backend():
    """
    El servicio que realmente habla con Trello.

    Se resuelve al vuelo y no al importar: asi el servidor arranca aunque
    todavia no haya credenciales, y cae al registro local (JSON) en vez de
    fallar. Un servidor MCP que no levanta no se puede ni inspeccionar.
    """
    from .servicio_trello import ServicioIncidenciasTrello, hay_credenciales

    if hay_credenciales():
        return ServicioIncidenciasTrello()

    from .servicio_json import ServicioIncidenciasJSON

    log.warning("sin credenciales de Trello: el servidor MCP escribe en el JSON local")
    return ServicioIncidenciasJSON()


def _como_dict(incidencia: Incidencia) -> dict:
    """Convierte la dataclass Incidencia en un diccionario para la respuesta estructurada MCP."""
    return dict(incidencia.__dict__)


# --------------------------------------------------------------------------
# Las cuatro herramientas que el agente SI puede usar.
#
# Los docstrings son el contrato que lee el modelo, igual que en una tool de
# LangChain: se escriben para el modelo, no para el programador.
# --------------------------------------------------------------------------

@mcp.tool()
def crear_ticket(
    descripcion: str, sesion_id: str, tipo: str = "otro", reserva_id: str = "",
) -> dict:
    """Registra una incidencia con el backend del servidor y devuelve sus datos estructurados.

    Incluye codigo, responsable declarado y plazo en horas. El backend puede
    conservar el caso solo en JSON si Trello falla; este resultado no acredita
    asignacion de un miembro de Trello ni notificacion efectiva al personal.

    Args:
        descripcion: que le ocurrio al cliente, en sus palabras, con la fecha si la menciono.
        sesion_id: identificador de la conversacion, para poder rastrear el caso.
        tipo: "espera", "servicio", "producto", "reserva" u "otro".
        reserva_id: codigo de la reserva relacionada, si la hay.
    """
    incidencia = _backend().crear_incidencia(
        sesion_id=sesion_id, descripcion=descripcion, tipo=tipo,
        reserva_id=reserva_id or None,
    )
    return _como_dict(incidencia)


@mcp.tool()
def consultar_ticket(ticket_id: str) -> dict:
    """Consulta el estado actual de un ticket ya abierto, para responderle a un cliente
    que pregunta por un reclamo anterior. El estado sale de la lista del tablero en la
    que este la tarjeta, asi que refleja lo que el equipo hizo con el caso.

    Args:
        ticket_id: codigo del ticket, por ejemplo I-4F2A9C.
    """
    buscado = ticket_id.strip().upper()
    for incidencia in _backend().listar_incidencias():
        if incidencia.id == buscado:
            return _como_dict(incidencia)
    return {"error": f"No existe el ticket {ticket_id}."}


@mcp.tool()
def listar_tickets(estado: str = "") -> list[dict]:
    """Lista los tickets del restaurante, opcionalmente filtrados por estado. Sirve para
    el panel del equipo y para revisar que casos quedaron sin atender.

    Args:
        estado: "abierta", "en_curso" o "cerrada". Vacio devuelve todos.
    """
    return [_como_dict(i) for i in _backend().listar_incidencias(estado or None)]


@mcp.tool()
def comentar_ticket(ticket_id: str, texto: str) -> str:
    """Deja una nota en un ticket existente, visible para el equipo del restaurante en la
    tarjeta. Sirve para anotar un dato que el cliente aporto despues, o una compensacion
    que el cliente pidio y que una persona tiene que aprobar.

    IMPORTANTE: comentar NO resuelve ni cierra el ticket, y anotar una compensacion no
    es aprobarla.

    Args:
        ticket_id: codigo del ticket, por ejemplo I-4F2A9C.
        texto: la nota para el equipo.
    """
    from .servicio_trello import ServicioIncidenciasTrello

    servicio = _backend()
    if not isinstance(servicio, ServicioIncidenciasTrello):
        if servicio.anotar(ticket_id.strip().upper(), texto):
            return f"Nota agregada al ticket {ticket_id.strip().upper()}."
        return "No se pudo registrar la nota: el caso no existe."

    try:
        servicio._cargar_tablero()
        buscado = ticket_id.strip().upper()
        tarjetas = servicio._pedir(
            "GET", f"/boards/{servicio._tablero_id}/cards", fields="name"
        )
        for tarjeta in tarjetas:
            if tarjeta.get("name", "").split("·")[0].strip() == buscado:
                servicio._pedir(
                    "POST", f"/cards/{tarjeta['id']}/actions/comments", text=texto
                )
                return f"Nota agregada al ticket {buscado}."
        return f"No existe el ticket {ticket_id} en el tablero."
    except Exception as error:
        return f"No se pudo comentar {ticket_id}: {error}"


# --------------------------------------------------------------------------
# Lo que este servidor NO expone, y es deliberado:
#
#   cerrar_ticket      el cierre lo confirma una persona, moviendo la tarjeta
#   mover_ticket       cambiar de lista es cambiar el estado: es del staff
#   borrar_ticket      un reclamo registrado no se borra
#   dar_compensacion   ninguna compensacion se comunica sin aprobacion humana
#
# No estan "prohibidas por el prompt": no existen. Un agente no puede llamar a
# una herramienta que el servidor no publica, y el listado de herramientas es
# justamente lo primero que un cliente MCP pide al conectarse.
# --------------------------------------------------------------------------


if __name__ == "__main__":
    # python -m app.incidencias.mcp_trello --http    -> servidor HTTP (demo)
    # python -m app.incidencias.mcp_trello           -> stdio (para clientes locales)
    from ..config import Config

    Config.desde_entorno()
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s | %(message)s")

    if "--http" in sys.argv:
        print(f"Servidor MCP de Clemente en http://localhost:{PUERTO_POR_DEFECTO}/mcp")
        print("Herramientas: crear_ticket, consultar_ticket, listar_tickets, comentar_ticket")
        mcp.run(transport="http", port=PUERTO_POR_DEFECTO)
    else:
        mcp.run()
