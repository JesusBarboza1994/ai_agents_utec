"""
Tools del Agente de Conocimiento (FAQs y politicas).

Una sola capacidad real: buscar en el catalogo validado (RAG). Si la
respuesta no esta ahi, el agente lo dice y escala -- no aproxima un horario
ni inventa una condicion.

El backend del indice (Chroma local o Azure AI Search, `RAG_BACKEND`) es
transparente para estas tools: solo llaman `buscar()` y citan la fuente que
devuelve cada `Fragmento`. Lo que cambio con Azure (PR #9) es el tipo de
error posible: un fallo remoto trae URL del endpoint, nombre del indice o
cuerpo HTTP. Nada de eso debe llegar al modelo, que podria repetirselo al
cliente; el detalle queda en la traza y el modelo recibe un aviso generico.
"""

from langchain.tools import ToolRuntime, tool

from . import con_traza

from ...observabilidad.trazas import registrar
from ..rag import buscar

FALLO_CATALOGO = (
    "No se pudo consultar el catálogo en este momento. No inventes la respuesta: "
    "dile al cliente que lo confirmas con el equipo del restaurante."
)


def _sesion(runtime: ToolRuntime) -> str:
    """Sesion del turno para la traza; 'desconocida' si el runtime no la trae."""
    return getattr(getattr(runtime, "context", None), "sesion_id", "desconocida")


def _consultar(pregunta: str, k: int, runtime: ToolRuntime, tool_nombre: str) -> list | None:
    """Llama `buscar()` y devuelve los fragmentos, o None si el indice fallo.

    El error (indice no construido, Ollama caido, Azure Search sin
    credenciales o con vectores de otra dimension) se registra completo en
    la traza `rag_error`; el texto de la excepcion nunca vuelve al modelo."""
    try:
        return buscar(pregunta, k=k)
    except Exception as error:
        registrar("rag_error", _sesion(runtime), agente=tool_nombre,
                  detalle={"error": f"{type(error).__name__}: {error}"[:300]})
        return None


def _citar(fragmentos: list) -> str:
    """Formatea cada fragmento como `[fuente] texto`, que es lo que el modelo cita."""
    return "\n\n".join(f"[{f.fuente}] {f.texto}" for f in fragmentos)


@tool
@con_traza
def buscar_en_catalogo(pregunta: str, runtime: ToolRuntime) -> str:
    """Busca en el catalogo validado del restaurante: horarios, ubicacion, carta,
    servicios, promociones y politicas. Es la unica fuente permitida para responder.

    Args:
        pregunta: la consulta del cliente, tal como la formulo.
    """
    fragmentos = _consultar(pregunta, 4, runtime, "buscar_en_catalogo")
    if fragmentos is None:
        return FALLO_CATALOGO
    if not fragmentos:
        return "El catalogo no tiene respuesta para esa consulta."
    return _citar(fragmentos)


@tool
@con_traza
def consultar_politica(tema: str, runtime: ToolRuntime) -> str:
    """Consulta una politica concreta (cancelacion, anticipacion, no-show, alergias,
    compensaciones, datos personales). Es la fuente unica que tambien usan los agentes
    de Reservas e Incidencias: nadie mantiene su propia copia.

    Args:
        tema: por ejemplo "cancelacion", "anticipacion", "grupos grandes".
    """
    fragmentos = _consultar(f"politica de {tema}", 3, runtime, "consultar_politica")
    if fragmentos is None:
        return FALLO_CATALOGO
    if not fragmentos:
        return f"No hay politica publicada sobre {tema}."
    return _citar(fragmentos)
