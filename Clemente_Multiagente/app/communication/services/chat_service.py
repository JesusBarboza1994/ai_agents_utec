"""Webchat conversation flow: in-memory session -> orchestrator -> session."""

from ...contratos import MensajeEntrante
from ...orquestador import responder as responder_orquestador
from ...orquestador.grafo import olvidar_sesion
from .sesiones import limpiar_sesion, obtener_sesion


def handle_incoming_message(entrante: MensajeEntrante):
    """Shared by every channel that goes through the in-memory session store."""
    sesion = obtener_sesion(entrante.sesion_id, entrante.canal)
    if entrante.nombre_cliente:
        sesion.nombre_cliente = entrante.nombre_cliente
    if entrante.telefono:
        sesion.telefono = entrante.telefono

    respuesta = responder_orquestador(entrante, historial=sesion.historial)

    sesion.agregar("user", entrante.texto)
    sesion.agregar("assistant", respuesta.texto)
    sesion.ultimo_agente = respuesta.agente
    return respuesta


def reset_session(session_id: str) -> None:
    """Forgets a thread's history and lets the planner start clean on the next message."""
    limpiar_sesion(session_id)
    olvidar_sesion(session_id)
