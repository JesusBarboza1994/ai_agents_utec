"""
Juez Claude del evaluador de LangSmith (langsmith/evaluador_langsmith.py).
Las evaluaciones solo usan Claude como juez. El evaluador DeepEval post-deploy
se elimino el 2026-10-10: LangSmith (criterios custom + openevals) lo reemplaza.

Por que Claude y no gpt-5.6-luna (el juez anterior, hasta el 2026-10-10):
  - El filtro de jailbreak de Azure OpenAI bloqueaba (400 content_filter) al
    propio JUEZ cuando el caso de prueba contenia el texto del ataque, asi que
    los casos de prompt injection quedaban sin puntaje.
  - El agente corre sobre gpt-5.6-luna: juzgarlo con otra familia de modelo
    evita que el juez premie a su propio modelo (sesgo de autopreferencia).

El agente evaluado sigue usando Azure OpenAI; esto solo cambia quien juzga.
"""

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
if not os.getenv("ANTHROPIC_API_KEY"):
    from dotenv import load_dotenv
    load_dotenv(RAIZ / ".env")

MODELO_JUEZ_CLAUDE = "claude-sonnet-5-5"


def modelo_del_juez() -> str:
    """`JUEZ_MODEL` si esta definido, si no claude-sonnet-5-5."""
    return os.getenv("JUEZ_MODEL") or MODELO_JUEZ_CLAUDE


def chat_claude_juez():
    """
    Juez Claude como chat model de LangChain (lo usan openevals y los criterios
    custom de LangSmith).

    - Sin `temperature`: Sonnet 5.5 rechaza valores no default con 400. Se fija
      effort "medium" (su default es "high"): juzgar es un prompt corto con
      salida corta y no necesita el razonamiento mas profundo.
    - fallbacks "default": si el clasificador de seguridad de Claude declina
      juzgar un caso adversarial, la API reintenta en otro modelo dentro de la
      misma llamada en vez de dejar el caso sin puntaje.
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "Falta ANTHROPIC_API_KEY: el juez de las evaluaciones es Claude "
            "(ver tests/evals/modelo_juez.py)."
        )
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=modelo_del_juez(),
        max_tokens=16000,
        output_config={"effort": "medium"},
        betas=["server-side-fallback-2026-07-01"],
        model_kwargs={"fallbacks": "default"},
        timeout=120,
        max_retries=2,
    )

