"""
Registro de incidencias -- lo consume el Agente de Incidencias y Experiencia.

Duena provisional: la dupla de agentes (Christian, Jean), hasta que el grupo
decida si este registro se integra al gestor de datos de Miguel. Mismo
patron que reservas: los agentes solo ven `obtener_servicio()`.
"""

from ..contratos import ServicioIncidencias

_servicio: ServicioIncidencias | None = None


def obtener_servicio() -> ServicioIncidencias:
    global _servicio
    if _servicio is None:
        from .servicio_json import ServicioIncidenciasJSON
        _servicio = ServicioIncidenciasJSON()
    return _servicio


def reiniciar_servicio() -> None:
    global _servicio
    _servicio = None
