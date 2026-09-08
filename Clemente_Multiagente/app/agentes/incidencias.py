"""
Agente de Incidencias y Experiencia.

El de mayor criticidad de los tres: lo que esta en juego es la retencion del
cliente. Convierte un mensaje de molestia en un caso con estado, plazo y
cierre verificable -- y se detiene antes de cualquier compensacion.
"""

from .base import construir_agente, ejecutar
from .contexto import ContextoConversacion
from .prompts import PROMPT_INCIDENCIAS
from .tools.catalogo_tools import consultar_politica
from .tools.incidencias_tools import (
    consultar_incidencia,
    registrar_incidencia,
    verificar_reserva_del_reclamo,
)

TOOLS = [
    registrar_incidencia,
    consultar_incidencia,
    verificar_reserva_del_reclamo,
    consultar_politica,   # marco de lo que se puede y no se puede proponer
]

_agente = None


def obtener_agente():
    global _agente
    if _agente is None:
        _agente = construir_agente(PROMPT_INCIDENCIAS, TOOLS)
    return _agente


def responder(
    texto: str, sesion_id: str, historial: list[dict] | None = None,
    contexto: ContextoConversacion | None = None,
) -> str:
    return ejecutar(
        obtener_agente(), texto, sesion_id, historial, contexto=contexto,
        fallback="Perdona, se me cruzo la linea. Me cuentas otra vez que paso y cuando fue?",
    )


def reiniciar() -> None:
    """Fuerza reconstruir el agente. Lo usan los tests y el banco de modelos:
    el modelo se resuelve al construirlo, asi que cambiar de modelo sin esto
    seguiria corriendo el anterior."""
    global _agente
    _agente = None
