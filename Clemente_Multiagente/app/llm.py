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
vez escribio la llamada a una herramienta como texto (ver README, seccion 10).
"""

import os

# Los modelos Claude 4.6 en adelante (opus-5, sonnet-5, opus-4-8/4-7/4-6,
# sonnet-4-6) ELIMINARON los parametros de muestreo: mandar `temperature`
# devuelve 400 "`temperature` is deprecated for this model". Solo los
# anteriores lo aceptan, asi que la temperatura se envia solo para esos.
CLAUDE_ACEPTA_TEMPERATURE = ("claude-haiku-4-5", "claude-sonnet-4-5", "claude-3")

# Embeddings del RAG. `bge-m3` es multilingue; `nomic-embed-text`, con el que
# empezo el proyecto, esta entrenado casi solo en ingles y NO discrimina en
# espanol: el 2026-09-07 se midio que para "tienen estacionamiento?" dejaba el
# fragmento con la palabra "estacionamiento" escrita dos veces en el puesto 7
# de 13, por debajo de la politica de cancelaciones. Las distancias de todos los
# fragmentos caian en la misma franja: no habia senal.
#
# Si alguna vez se vuelve a `nomic-embed-text`, hay que anteponer sus prefijos de
# tarea ("search_query: " a la consulta y "search_document: " a cada fragmento);
# el modelo los exige y `OllamaEmbeddings` no los agrega. Aun asi rinde peor que
# `bge-m3` en espanol.
MODELO_EMBEDDINGS_OLLAMA = "bge-m3"

# Modelos locales via Ollama. Se quedan como respaldo, no como default.
MODELOS_OLLAMA = {
    "llama3.2": "llama3.2:latest",
    "llama3.2:1b": "llama3.2:1b",
    "phi4-mini": "phi4-mini:latest",
    "qwen3": "qwen3:0.6b",
}

# Los modelos de razonamiento de OpenAI (gpt-5 en adelante, gpt-6, serie o)
# tampoco aceptan `temperature`: solo admiten el valor por defecto. Es el mismo
# problema que ya teniamos con Claude 4.6+, en la otra casa.
OPENAI_SIN_TEMPERATURE = ("gpt-5", "gpt-6", "o1", "o3", "o4")

# Descubierto el 2026-09-08 con una reproduccion minima (ver bitacora): estos
# mismos modelos, en `/v1/chat/completions`, RECHAZAN un turno que traiga
# herramientas de funcion si el razonamiento extendido esta activo:
#
#   "Function tools with reasoning_effort are not supported for gpt-5.6-terra
#    in /v1/chat/completions. To use function tools, use /v1/responses or set
#    reasoning_effort to 'none'."
#
# Los tres nodos del proyecto usan herramientas -- hasta el orquestador
# respondiendo informacion tiene dos --, asi que sin esto ningun turno con
# OpenAI llegaba a responder: caia siempre en el error generico del orquestador
# (ver `grafo.responder`).
#
# OJO, esto NO cubre a gpt-6: se probo por separado (gpt-6-astra) y la API
# devuelve un segundo error distinto --
#
#   "Unsupported value: 'reasoning_effort' does not support 'none' with this
#    model. Supported values are: 'low', 'medium', 'high', and 'xhigh'."
#
# -- y forzando cualquiera de esos cuatro valores vuelve el error original de
# arriba. Es un callejon sin salida real de la propia API: gpt-6 exige
# razonamiento, no admite apagarlo, y con razonamiento activo no admite
# herramientas de funcion en este endpoint. NO hay combinacion de parametros
# que lo resuelva; la unica salida seria migrar a `/v1/responses`, fuera del
# alcance de esta correccion. Por eso gpt-6 NO esta en esta lista: mandarle
# "none" solo cambia un error por otro, y dejarlo sin el parametro reproduce
# el error original, que al menos es el mas claro de los dos.
#
# o1/o3/o4 quedan igual que antes por prefijo (no se verificaron: el proyecto
# no usa esos IDs en ningun lado, se listan solo por si alguien los prueba).
OPENAI_SIN_RAZONAMIENTO = ("gpt-5", "o1", "o3", "o4")

# Precio por millon de tokens (entrada, salida), en dolares.
#
# Verificado el 2026-09-07 contra las paginas oficiales:
#   Anthropic  https://platform.claude.com/docs/en/about-claude/pricing
#   OpenAI     https://developers.openai.com/api/docs/pricing
#
# NO se estima ningun precio: si un modelo no esta en esta tabla, el banco de
# pruebas reporta sus tokens y deja el costo vacio, en vez de inventar un numero.
# Revisar esta tabla antes de citarla en el informe: los precios cambian, y el de
# gpt-5.6-sol es promocional (anunciado al menos hasta el 2026-11-21).
PRECIOS_POR_MILLON = {
    # Anthropic
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    # OpenAI
    "gpt-6-astra": (10.0, 50.0),
    "gpt-5.6-sol": (4.0, 20.0),
    "gpt-5.6-terra": (2.0, 12.0),
    "gpt-5.6-luna": (0.20, 1.20),
    "gpt-5.5": (5.0, 30.0),
    "gpt-5.4": (2.50, 15.0),
    "gpt-4o-mini": (0.15, 0.60),
}


def precio_de(modelo: str) -> tuple[float, float] | None:
    """Precio (entrada, salida) por millon de tokens, o None si no lo conocemos."""
    if modelo in PRECIOS_POR_MILLON:
        return PRECIOS_POR_MILLON[modelo]
    # Los IDs con sufijo de fecha ("gpt-5.4-2026-03-05") cuestan lo mismo que su
    # alias sin fecha, asi que se acepta el prefijo mas largo que coincida.
    coincidencias = [k for k in PRECIOS_POR_MILLON if modelo.startswith(k)]
    return PRECIOS_POR_MILLON[max(coincidencias, key=len)] if coincidencias else None


def costo(modelo: str, tokens_entrada: int, tokens_salida: int) -> float | None:
    """Costo en dolares de una corrida, o None si el modelo no tiene precio conocido."""
    tarifa = precio_de(modelo)
    if tarifa is None:
        return None
    entrada, salida = tarifa
    return (tokens_entrada * entrada + tokens_salida * salida) / 1_000_000


def modelo_activo() -> str:
    """
    ID del modelo que se usaria ahora mismo. Lo usan el banco y los informes.

    Respeta `AGENT_MODEL`: si el backend es openai, devuelve el modelo de OpenAI
    aunque `ANTHROPIC_MODEL` este definida. Parece obvio y no lo era: el registro
    de conversaciones leia `ANTHROPIC_MODEL or OPENAI_MODEL` y escribia el modelo
    equivocado en cada turno cuando el `.env` tenia las dos.
    """
    backend = os.getenv("AGENT_MODEL", "openai")
    if backend == "claude":
        return os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
    if backend == "openai":
        return os.getenv("OPENAI_MODEL", "gpt-5.6-terra")
    return MODELOS_OLLAMA.get(backend, backend)


def proveedor_de(modelo: str) -> str:
    """
    De que casa es un ID de modelo. Sin adivinar: prefijos conocidos.

    Lo necesitan el juez y el banco, que reciben un modelo concreto por linea de
    comandos y tienen que saber a que API mandarlo, sin depender de como este el
    `.env` en ese momento.
    """
    if modelo.startswith("claude"):
        return "claude"
    if modelo.startswith(("gpt", "o1", "o3", "o4")):
        return "openai"
    if modelo in MODELOS_OLLAMA:
        return modelo
    raise ValueError(
        f"No se de que proveedor es {modelo!r}. Usa un ID que empiece con "
        f"'claude' o con 'gpt'/'o', o uno de: {', '.join(MODELOS_OLLAMA)}."
    )


def resolver_modelo(temperature: float = 0.2, rol: str = "agente", modelo: str | None = None):
    """
    Devuelve el chat model ya instanciado segun AGENT_MODEL.

    `rol` permite que el enrutador use un modelo distinto al de los agentes.
    Tiene sentido porque hacen trabajos distintos: el enrutador clasifica con
    salida estructurada -- una decision, sin herramientas -- pero corre en CADA
    turno; los agentes encadenan llamadas a tools y redactan la respuesta que ve
    el cliente. Si `ANTHROPIC_MODEL_ENRUTADOR` no esta definida, los dos usan el
    mismo modelo y no cambia nada.

    `modelo` fuerza un ID concreto y **gana sobre el `.env`**, incluida la casa:
    pedir `claude-opus-5` con `AGENT_MODEL=openai` devuelve Opus, no un GPT.

    Ese parametro no estaba, y su ausencia causo un error serio: el juez de las
    evaluaciones calculaba bien su nombre pero construia el modelo leyendo el
    `.env`, asi que el informe DECLARABA `claude-opus-5` y en realidad juzgaba
    con el mismo modelo que estaba evaluando. Es exactamente el sesgo de
    auto-preferencia contra el que advierte ese mismo informe. La prueba
    `tests/test_llm.py` compara el modelo REAL, no el nombre, para que no pueda
    volver a pasar en silencio.
    """
    agent_model = proveedor_de(modelo) if modelo else os.getenv("AGENT_MODEL", "openai")

    if agent_model == "claude":
        from langchain_anthropic import ChatAnthropic

        # IDs validos (sin sufijo de fecha): claude-opus-5 (1M de contexto,
        # 5 y 25 dolares por millon de tokens de entrada y salida),
        # claude-sonnet-5 (1M, 2 y 10) y claude-haiku-4-5 (200K, 1 y 5).
        elegido = modelo or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
        if modelo is None and rol == "enrutador":
            elegido = os.getenv("ANTHROPIC_MODEL_ENRUTADOR") or elegido
        parametros = {"model": elegido, "timeout": 60, "max_retries": 2}
        if elegido.startswith(CLAUDE_ACEPTA_TEMPERATURE):
            parametros["temperature"] = temperature
        return ChatAnthropic(**parametros)

    if agent_model == "openai":
        from langchain_openai import ChatOpenAI

        elegido = modelo or os.getenv("OPENAI_MODEL", "gpt-5.6-terra")
        if modelo is None and rol == "enrutador":
            elegido = os.getenv("OPENAI_MODEL_ENRUTADOR") or elegido
        parametros = {"model": elegido, "timeout": 60, "max_retries": 2}
        if not elegido.startswith(OPENAI_SIN_TEMPERATURE):
            parametros["temperature"] = temperature
        if elegido.startswith(OPENAI_SIN_RAZONAMIENTO):
            # Sin esto, cualquier turno con herramientas de funcion (los tres
            # nodos del proyecto las usan) devuelve 400 de la API. Ver el
            # comentario de OPENAI_SIN_RAZONAMIENTO mas arriba.
            parametros["reasoning_effort"] = "none"
        return ChatOpenAI(**parametros)

    if agent_model == "azure":
        from langchain_openai import AzureChatOpenAI

        # El deployment de Azure se nombra igual que el modelo base (convencion
        # de este proyecto), asi que los mismos prefijos de OPENAI_SIN_TEMPERATURE
        # y OPENAI_SIN_RAZONAMIENTO aplican sin cambios.
        elegido = modelo or os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5.6-luna")
        parametros = {
            "azure_deployment": elegido,
            "azure_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
            "api_version": os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
            "timeout": 60,
            "max_retries": 2,
        }
        if not elegido.startswith(OPENAI_SIN_TEMPERATURE):
            parametros["temperature"] = temperature
        if elegido.startswith(OPENAI_SIN_RAZONAMIENTO):
            parametros["reasoning_effort"] = "none"
        return AzureChatOpenAI(**parametros)

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
        f"AGENT_MODEL desconocido: {agent_model!r}. Opciones: claude, openai, azure, "
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
            model=os.getenv("OLLAMA_EMBEDDINGS_MODEL", MODELO_EMBEDDINGS_OLLAMA),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )

    raise ValueError(f"EMBEDDINGS_BACKEND desconocido: {backend!r}. Opciones: ollama, openai")


def nombre_embeddings() -> str:
    """Etiqueta del modelo de embeddings activo, para versionar la coleccion de Chroma."""
    backend = os.getenv("EMBEDDINGS_BACKEND", "ollama")
    if backend == "openai":
        return os.getenv("OPENAI_EMBEDDINGS_MODEL", "text-embedding-3-small")
    return os.getenv("OLLAMA_EMBEDDINGS_MODEL", MODELO_EMBEDDINGS_OLLAMA)


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
