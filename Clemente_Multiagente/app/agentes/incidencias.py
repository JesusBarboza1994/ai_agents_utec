"""
Agente de Incidencias y Experiencia -- STUB TEMPORAL.

Implementacion real: Christian y Jean, rama `feat/agentes-incidencias`.

El agente definitivo registra el reclamo con estado, responsable y plazo
(`registrar_incidencia`), verifica si habia reserva de por medio y se detiene
antes de cualquier compensacion: no tiene tool para cerrar una incidencia ni
para ofrecer cortesias.

Este stub solo respeta la firma para que el sistema completo arranque.
"""


def responder(texto: str, sesion_id: str, historial: list[dict] | None = None) -> str:
    return (
        "Lamento lo que ocurrio. Estoy registrando tu caso para que el equipo "
        "del restaurante lo revise y te responda."
    )
