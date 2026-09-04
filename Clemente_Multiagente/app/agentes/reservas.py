"""
Agente de Reservas y Capacidad -- STUB TEMPORAL.

Implementacion real: Christian y Jean, rama `feat/agentes-reservas`.

El agente definitivo se construye con `create_agent` de LangChain sobre siete
tools (consultar_disponibilidad, crear_reserva, buscar_mis_reservas,
modificar_reserva, cancelar_reserva, escalar_a_staff, consultar_politica) y
hace cumplir por construccion los limites del Entregable 01: no afirma
disponibilidad sin consultarla, no registra sin confirmacion explicita del
cliente, y escala los grupos de mas de 10 personas.

Este stub solo respeta la firma para que el sistema completo arranque.
"""


def responder(texto: str, sesion_id: str, historial: list[dict] | None = None) -> str:
    return (
        "Estoy revisando la disponibilidad para tu solicitud. "
        "En un momento te confirmo la mesa desde el restaurante."
    )
