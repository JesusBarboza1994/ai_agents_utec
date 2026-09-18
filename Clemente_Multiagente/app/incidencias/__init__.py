"""
Registro de incidencias -- lo consume el Agente de Incidencias (customer care).

Duena provisional: la dupla de agentes (Christian, Jean), hasta que el grupo
decida si este registro se integra al gestor de datos de Miguel. Mismo
patron que reservas: los agentes solo ven `obtener_servicio()`.

Backend, decidido en la asesoria del 2026-09-07 (Acuerdo 4): si hay credenciales
de Trello en el `.env`, los tickets van a Trello, que es donde el staff los
trabaja y desde donde le llega la notificacion. Si no las hay, el proyecto sigue
corriendo contra el JSON local -- para los tests, para la evaluacion y para
cualquiera del equipo que clone el repo sin tablero.
"""

import logging
import os

from ..contratos import ServicioIncidencias

log = logging.getLogger("clemente")

_servicio: ServicioIncidencias | None = None


BACKENDS = ("mcp", "trello", "json")


def backend_activo() -> str:
    """
    Cual de los tres backends esta activo: "mcp", "trello" o "json".

    Los tres implementan el mismo contrato y escriben en el mismo tablero; lo
    que cambia es por donde pasa la llamada:

        mcp     -> servidor MCP -> API de Trello   (el camino de la Sesion 16)
        trello  -> API de Trello                   (directo, respaldo)
        json    -> archivo local                   (sin credenciales)

    Con `auto` gana MCP si hay credenciales de Trello, porque es el camino que
    ademas impone el limite de permisos por fuera del proceso del agente. Se
    fuerza uno concreto con CLEMENTE_BACKEND_INCIDENCIAS.
    """
    from .servicio_trello import hay_credenciales

    pedido = os.getenv("CLEMENTE_BACKEND_INCIDENCIAS", "auto").lower()
    if pedido in BACKENDS:
        return pedido
    return "mcp" if hay_credenciales() else "json"


def obtener_servicio() -> ServicioIncidencias:
    """Selecciona JSON, Trello o MCP con backend_activo y reutiliza la instancia del proceso."""
    global _servicio
    if _servicio is None:
        backend = backend_activo()
        if backend == "mcp":
            from .servicio_mcp import ServicioIncidenciasMCP

            _servicio = ServicioIncidenciasMCP()
            destino = os.getenv("TRELLO_MCP_URL") or "en memoria"
            log.info("Incidencias: backend MCP activo (%s) -> Trello", destino)
        elif backend == "trello":
            from .servicio_trello import ServicioIncidenciasTrello

            _servicio = ServicioIncidenciasTrello()
            log.info("Incidencias: backend Trello directo (sin MCP)")
        else:
            from .servicio_json import ServicioIncidenciasJSON

            _servicio = ServicioIncidenciasJSON()
            log.info("Incidencias: backend JSON local (sin credenciales de Trello)")
    return _servicio


def reiniciar_servicio() -> None:
    """Descarta la instancia en memoria para reconstruirla con la configuracion vigente."""
    global _servicio
    _servicio = None
