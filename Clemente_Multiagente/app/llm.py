"""
Resolucion del backend de LLM y de embeddings, en un solo lugar.

Mismo patron que `_utils.py` de las Sesiones 14 y 15: ningun agente instancia
un modelo por su cuenta, todos piden `resolver_modelo(temperature=...)`. Asi
el equipo cambia de proveedor con una variable de entorno, sin tocar el
codigo de ningun agente ni del grafo.

Decision del equipo (acordada en reunion): el razonamiento corre sobre API de
**Anthropic** u **OpenAI**. Los modelos locales de Ollama quedan como plan B
para trabajar sin conexion o sin gastar credito -- en la prueba del 2026-09-03
`llama3.2` invento datos del catalogo, invento un codigo de incidencia y una
vez escribio la llamada a una herramienta como texto (ver README, seccion 6).
"""

import os

# Modelos locales via Ollama. Se quedan como respaldo, no como default.
MODELOS_OLLAMA = {
    "llama3.2": "llama3.2:latest",
    "llama3.2:1b": "llama3.2:1b",
    "phi4-mini": "phi4-mini:latest",
    "qwen3": "qwen3:0.6b",
}


def resolver_modelo(temperature: float = 0.2):
    """Devuelve el chat model ya instanciado segun AGENT_MODEL."""
    agent_model = os.getenv("AGENT_MODEL", "claude")

    if agent_model == "claude":
        from langchain_anthropic import ChatAnthropic

        # IDs validos (sin sufijo de fecha): claude-opus-5 (1M de contexto,
        # 5 y 25 dolares por millon de tokens de entrada y salida),
        # claude-sonnet-5 (1M, 2 y 10) y claude-haiku-4-5 (200K, 1 y 5).
        return ChatAnthropic(
            model=os.getenv("ANTHROPIC_MODEL", "claude-opus-5"),
            temperature=temperature,
            timeout=60,
            max_retries=2,
        )

    if agent_model == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=temperature,
            timeout=60,
            max_retries=2,
        )

    if agent_model in MODELOS_OLLAMA:
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=MODELOS_OLLAMA[agent_model],
            temperature=temperature,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )

    if agent_model == "gemma-lmstudio":
        # LM Studio expone un servidor local compatible con la API de OpenAI.
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=os.getenv("LMSTUDIO_MODEL", "google/gemma-4-e4b"),
            base_url=os.getenv("LMSTUDIO_BASE_URL", "http://172.30.32.1:8666/v1"),
            api_key="lm-studio",
            temperature=temperature,
        )

    raise ValueError(
        f"AGENT_MODEL desconocido: {agent_model!r}. Opciones: claude, openai, "
        f"{', '.join(MODELOS_OLLAMA)}, gemma-lmstudio"
    )


def resolver_embeddings():
    """
    Modelo de embeddings del RAG, segun EMBEDDINGS_BACKEND.

    OJO: los vectores de dos modelos distintos NO son comparables. Si el
    equipo cambia de backend hay que reconstruir el indice
    (`python -m app.agentes.rag.indice --reindexar`); por eso el nombre del
    modelo entra en el nombre de la coleccion de Chroma.
    """
    backend = os.getenv("EMBEDDINGS_BACKEND", "ollama")

    if backend == "openai":
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(model=os.getenv("OPENAI_EMBEDDINGS_MODEL", "text-embedding-3-small"))

    if backend == "ollama":
        from langchain_ollama import OllamaEmbeddings

        return OllamaEmbeddings(
            model=os.getenv("OLLAMA_EMBEDDINGS_MODEL", "nomic-embed-text"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )

    raise ValueError(f"EMBEDDINGS_BACKEND desconocido: {backend!r}. Opciones: ollama, openai")


def nombre_embeddings() -> str:
    """Etiqueta del modelo de embeddings activo, para versionar la coleccion de Chroma."""
    backend = os.getenv("EMBEDDINGS_BACKEND", "ollama")
    if backend == "openai":
        return os.getenv("OPENAI_EMBEDDINGS_MODEL", "text-embedding-3-small")
    return os.getenv("OLLAMA_EMBEDDINGS_MODEL", "nomic-embed-text")


def extraer_texto(mensaje) -> str:
    """Texto plano de un AIMessage, ignorando bloques de razonamiento extendido."""
    contenido = getattr(mensaje, "content", mensaje)
    if isinstance(contenido, str):
        return contenido.strip()
    partes = [
        bloque.get("text", "")
        for bloque in contenido
        if isinstance(bloque, dict) and bloque.get("type") == "text"
    ]
    return "\n".join(partes).strip()
