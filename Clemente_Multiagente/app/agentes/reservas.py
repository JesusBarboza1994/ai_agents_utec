"""
Agente de Reservas y Capacidad.

Es el unico de los tres que escribe un compromiso que el restaurante tendra
que honrar en sala; por eso es el que mas control lleva encima: doble
verificacion de disponibilidad, confirmacion explicita del cliente y limite
duro de grupo antes de escalar.
"""

from .base import construir_agente, ejecutar
from .contexto import ContextoConversacion
from .prompts import PROMPT_RESERVAS
from .tools.catalogo_tools import consultar_politica
from .tools.reservas_tools import (
    buscar_mis_reservas,
    cancelar_reserva,
    consultar_disponibilidad,
    consultar_reserva_por_codigo,
    crear_reserva,
    escalar_a_staff,
    modificar_reserva,
)

TOOLS = [
    consultar_disponibilidad,
    crear_reserva,
    buscar_mis_reservas,
    consultar_reserva_por_codigo,   # el cliente suele traer el codigo, no el telefono
    modificar_reserva,
    cancelar_reserva,
    escalar_a_staff,
    consultar_politica,   # fuente unica de verdad: no duplicamos las politicas aqui
]

_agente = None


def obtener_agente():
    """Construccion perezosa: el modelo se instancia en el primer mensaje, no al importar."""
    global _agente
    if _agente is None:
        _agente = construir_agente(PROMPT_RESERVAS, TOOLS)
    return _agente


def responder(
    texto: str, sesion_id: str, historial: list[dict] | None = None,
    contexto: ContextoConversacion | None = None,
) -> str:
    return ejecutar(
        obtener_agente(), texto, sesion_id, historial, contexto=contexto,
        fallback="Perdona, se me cruzo la linea. Me confirmas fecha, hora y cuantas personas son?",
    )


def reiniciar() -> None:
    """Fuerza reconstruir el agente. Lo usan los tests y el banco de modelos:
    el modelo se resuelve al construirlo, asi que cambiar de modelo sin esto
    seguiria corriendo el anterior."""
    global _agente
    _agente = None
