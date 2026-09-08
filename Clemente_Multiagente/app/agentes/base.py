"""
Andamiaje comun de los tres agentes.

Todos se construyen igual (`create_agent` de LangChain 1.x, Sesion 12) y se
ejecutan igual. Lo unico que cambia entre ellos es su prompt de sistema y su
caja de tools -- que es exactamente la tesis del Entregable 01: tres agentes
distintos porque tienen distinto alcance y distinto costo de equivocarse, no
porque usen tecnologia distinta.

Aqui viven tres cosas transversales:
  1. el contexto de conversacion que reciben las tools (`context_schema`),
  2. la ficha del cliente de memoria de largo plazo, inyectada en cada turno,
  3. el guardrail de salida que descarta tool-calls escritas como texto.
"""

import json
import warnings
from datetime import date

from ..llm import extraer_texto, resolver_modelo
from ..observabilidad.trazas import registrar
from .contexto import ContextoConversacion
from .memoria import ficha_del_cliente
from .prompts import AVISO_FICHA

# Historial que se le pasa a un agente: solo turnos de texto (user/assistant).
# Los mensajes de tool no viajan entre agentes porque cada uno tiene tools
# distintas y un mensaje de tool huerfano rompe la conversacion.
LIMITE_TURNOS_HISTORIAL = 12

# LangChain serializa el estado del grafo con Pydantic y avisa de que el campo
# `context` no es None. Es cosmetico -- el contexto SI llega a las tools, lo
# prueban tests/test_guardrails.py -- pero ensucia la consola de la demo.
warnings.filterwarnings("ignore", message=".*Pydantic serializer warnings.*", category=UserWarning)


def construir_agente(prompt_sistema: str, tools: list, temperature: float = 0.1):
    """
    create_agent con el modelo del proyecto. Temperatura baja: aqui no se crea, se opera.

    `context_schema` es lo que permite que las tools reciban el `sesion_id` sin
    pedirselo al modelo, y que devuelvan `escalado` y `datos` al orquestador.
    """
    from langchain.agents import create_agent

    return create_agent(
        model=resolver_modelo(temperature=temperature),
        system_prompt=f"{prompt_sistema}\n\nFecha de hoy: {date.today().isoformat()}.",
        tools=tools,
        context_schema=ContextoConversacion,
    )


# Claves tipicas de una llamada a herramienta escrita como texto.
_CLAVES_DE_TOOL = {"name", "parameters", "arguments", "tool", "function", "tool_call"}


def _parece_llamada_de_tool(texto: str) -> bool:
    """
    Detecta la falla mas comun de los modelos locales chicos (llama3.2): en vez
    de INVOCAR la herramienta, escriben la llamada como JSON en su respuesta --
    a veces con un nombre de tool que ni siquiera existe. Si eso llegara al
    cliente, veria basura tecnica en el chat.

    Es un guardrail de reflejo simple: no interpreta, solo corta.
    """
    limpio = texto.strip().strip("`").removeprefix("json").strip()
    if not limpio.startswith("{"):
        return False
    try:
        datos = json.loads(limpio)
    except json.JSONDecodeError:
        return False
    return isinstance(datos, dict) and bool(_CLAVES_DE_TOOL & set(datos))


def ejecutar(
    agente, texto: str, sesion_id: str, historial: list[dict] | None = None,
    fallback: str = "Disculpa, no te entendi bien. Me lo repites?",
    contexto: ContextoConversacion | None = None,
) -> str:
    """
    Invoca al agente y devuelve solo su texto de respuesta.

    El `sesion_id` no entra al prompt: viaja en el contexto de ejecucion, que las
    tools leen con `runtime: ToolRuntime`. Lo que si se inyecta en el turno es la
    **ficha del cliente** (memoria de largo plazo): quien es y que reservas tiene,
    para que el agente no dependa de que el cliente repita sus datos en cada
    conversacion nueva.
    """
    contexto = contexto or ContextoConversacion(sesion_id=sesion_id)

    mensajes = list(historial or [])[-LIMITE_TURNOS_HISTORIAL:]
    ficha = ficha_del_cliente(sesion_id)
    # La instruccion de como tratar la ficha viaja PEGADA a la ficha, no en el
    # system prompt: si el cliente es nuevo no hay ficha, y entonces no se paga
    # ni un token explicando que hacer con algo que no llego. Es el recorte de
    # contexto que pidio Boris en la asesoria del 2026-09-07 [08:22].
    entrada = f"[{AVISO_FICHA}: {ficha}]\n{texto}" if ficha else texto
    if ficha:
        # La ficha entra por el prompt, no por una tool, asi que sin esta traza
        # el agente puede citar la reserva de un cliente y en el registro no
        # queda constancia de donde salio el dato. Lo senalo la evaluacion del
        # 2026-09-07: "no hay evidencia de que estos datos provengan de una
        # consulta real al sistema". La habia, pero no era auditable.
        registrar("ficha", sesion_id, detalle={"ficha": ficha})
    mensajes.append({"role": "user", "content": entrada})

    resultado = agente.invoke(
        {"messages": mensajes}, config={"recursion_limit": 12}, context=contexto
    )
    respuesta = extraer_texto(resultado["messages"][-1])

    if _parece_llamada_de_tool(respuesta):
        # Queda registrado: es la metrica que decide si el modelo alcanza para la
        # demo o hay que cambiarlo (ver ACUERDOS_EQUIPO.md, punto 7.3).
        registrar(
            "guardrail", sesion_id,
            detalle={"motivo": "el modelo escribio la tool en vez de invocarla",
                     "texto": respuesta[:200]},
        )
        return fallback

    return respuesta
