"""
El orquestador respondiendo por si mismo: la funcion de *proxy*.

Boris, en la asesoria del 2026-09-07 [12:09]: "este orquestador no solo va a
definir el plan, sino que va a hacer algo mas: va a servir de proxy a cualquier
pedido de informacion del restaurante".

Esto NO es un cuarto agente. Es el orquestador usando sus propias herramientas.
La diferencia importa para la profile card y para la defensa: no tiene alcance
de negocio propio, no puede escribir nada, y no aparece en el registro `AGENTES`.
Por eso vive en `app/orquestador/` y no en `app/agentes/`.

Que gana el sistema con esto, ademas de un agente menos:
  * una pregunta general se contesta en un solo salto, sin pagar una llamada de
    clasificacion mas otra de respuesta;
  * el orquestador conoce los horarios y la direccion, asi que puede decidir con
    esos datos en la mano -- si el cliente pide mesa un lunes, sabe que el
    restaurante esta cerrado antes de mandarlo a Reservas.
"""

from ..agentes.base import construir_agente, ejecutar
from ..agentes.contexto import ContextoConversacion
from ..agentes.prompts import PROMPT_ORQUESTADOR
from ..agentes.tools.catalogo_tools import buscar_en_catalogo, consultar_politica

# Las unicas dos herramientas del orquestador, y las dos son de LECTURA. Es un
# guardrail estructural, no una instruccion: aunque el prompt fallara, no tiene
# con que reservar, cobrar ni cerrar un reclamo.
TOOLS = [buscar_en_catalogo, consultar_politica]

_agente = None


def obtener_agente():
    global _agente
    if _agente is None:
        _agente = construir_agente(PROMPT_ORQUESTADOR, TOOLS)
    return _agente


def responder(
    texto: str, sesion_id: str, historial: list[dict] | None = None,
    contexto: ContextoConversacion | None = None,
) -> str:
    """Misma firma que los agentes, para que el grafo trate a todos los nodos igual."""
    return ejecutar(
        obtener_agente(), texto, sesion_id, historial, contexto=contexto,
        fallback="Perdona, se me cruzo la linea. Me repites tu consulta?",
    )


def reiniciar() -> None:
    """Fuerza reconstruir el agente: lo usan los tests y el banco de modelos."""
    global _agente
    _agente = None
