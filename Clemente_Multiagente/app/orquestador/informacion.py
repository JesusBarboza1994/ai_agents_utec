"""
El orquestador respondiendo por si mismo: la funcion de *proxy*.

Boris, en la asesoria del 2026-09-07 [12:09]: "este orquestador no solo va a
definir el plan, sino que va a hacer algo mas: va a servir de proxy a cualquier
pedido de informacion del restaurante".

Es el componente de informacion del orquestador. Tecnicamente se construye
con create_agent de LangChain, pero no se registra como un agente de negocio
independiente en AGENTES. Sus herramientas solo leen catalogo y politicas.
Por eso vive en app/orquestador/ y no en app/agentes/.

El recorrido normal sigue pasando por el planificador antes de este nodo;
una consulta general puede consumir una llamada de planificacion y las
llamadas del agente para recuperar y redactar. El planificador recibe el
hilo y ultimo_agente, no los fragmentos del catalogo de este componente.
"""

from ..agentes.base import construir_agente, ejecutar
from ..agentes.contexto import ContextoConversacion
from ..agentes.prompts import PROMPT_ORQUESTADOR
from ..agentes.tools.catalogo_tools import buscar_en_catalogo, consultar_politica
from ..agentes.tools.fecha_tools import get_current_datetime

# Las tres herramientas del orquestador son de LECTURA. Es un guardrail
# estructural, no una instruccion: aunque el prompt fallara, no tiene con que
# reservar, cobrar ni cerrar un reclamo. La fecha sirve para "abren manana?":
# el horario depende del dia de la semana.
TOOLS = [buscar_en_catalogo, consultar_politica, get_current_datetime]

_agente = None


def obtener_agente():
    """Construye y reutiliza el agente LangChain del componente de informacion del orquestador.

    Solo recibe herramientas de lectura del catalogo y politicas; no se
    registra como agente de negocio independiente en AGENTES."""
    global _agente
    if _agente is None:
        _agente = construir_agente(PROMPT_ORQUESTADOR, TOOLS)
    return _agente


def responder(
    texto: str, sesion_id: str, historial: list[dict] | None = None,
    contexto: ContextoConversacion | None = None,
) -> str:
    """Responde una consulta general con el agente de lectura del orquestador.

    Recibe texto, sesion, historial y contexto y devuelve el texto de ejecutar.
    Las herramientas recuperan catalogo y politicas; este componente no crea
    reservas ni incidencias. El fallback sustituye una tool escrita como
    texto; los errores de invocacion se propagan al llamador.
    """
    return ejecutar(
        obtener_agente(), texto, sesion_id, historial, contexto=contexto,
        fallback="Perdona, se me cruzo la linea. Me repites tu consulta?",
    )


def reiniciar() -> None:
    """Fuerza reconstruir el agente: lo usan los tests y el banco de modelos."""
    global _agente
    _agente = None
