"""
Tools del Agente de Conocimiento (FAQs y politicas).

Una sola capacidad real: buscar en el catalogo validado (RAG). Si la
respuesta no esta ahi, el agente lo dice y escala -- no aproxima un horario
ni inventa una condicion.
"""

from langchain.tools import ToolRuntime, tool

from . import con_traza

from ..rag import buscar


@tool
@con_traza
def buscar_en_catalogo(pregunta: str, runtime: ToolRuntime) -> str:
    """Busca en el catalogo validado del restaurante: horarios, ubicacion, carta,
    servicios, promociones y politicas. Es la unica fuente permitida para responder.

    Args:
        pregunta: la consulta del cliente, tal como la formulo.
    """
    try:
        fragmentos = buscar(pregunta, k=4)
    except Exception as error:  # indice no construido, Ollama caido, etc.
        return f"No se pudo consultar el catalogo ({error}). Escalar al equipo del restaurante."

    if not fragmentos:
        return "El catalogo no tiene respuesta para esa consulta."

    return "\n\n".join(f"[{f.fuente}] {f.texto}" for f in fragmentos)


@tool
@con_traza
def consultar_politica(tema: str, runtime: ToolRuntime) -> str:
    """Consulta una politica concreta (cancelacion, anticipacion, no-show, alergias,
    compensaciones, datos personales). Es la fuente unica que tambien usan los agentes
    de Reservas e Incidencias: nadie mantiene su propia copia.

    Args:
        tema: por ejemplo "cancelacion", "anticipacion", "grupos grandes".
    """
    try:
        fragmentos = buscar(f"politica de {tema}", k=3)
    except Exception as error:
        return f"No se pudo consultar la politica ({error})."

    if not fragmentos:
        return f"No hay politica publicada sobre {tema}."
    return "\n\n".join(f"[{f.fuente}] {f.texto}" for f in fragmentos)
