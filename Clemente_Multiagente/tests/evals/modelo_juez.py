"""
Juez gpt-5.6-luna compartido por los dos evaluadores copiados de la tarea grupal
(deepeval/evaluador_deepeval.py, langsmith/evaluador_langsmith.py).

Por que no se reusa `app.llm.resolver_modelo` directamente: esa funcion decide
el proveedor por el PREFIJO del nombre del modelo (`proveedor_de`), y todo lo
que empieza con "gpt" se manda por la rama de OpenAI nativo -- pero en este
`.env` no hay `OPENAI_API_KEY`, solo `AZURE_OPENAI_API_KEY`. `gpt-5.6-luna` es
el nombre del *deployment* de Azure de este proyecto (ver `app/llm.py`, rama
`azure`), no un modelo accesible via la API publica de OpenAI. Forzar el
nombre a traves de `resolver_modelo(modelo="gpt-5.6-luna")` habria fallado por
falta de `OPENAI_API_KEY`, asi que este archivo replica exactamente la misma
rama `azure` de `app/llm.py`, fijando el deployment a "gpt-5.6-luna" sin
depender de `AGENT_MODEL` (que en este `.env` esta en `llama3.2`).
"""

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
if not os.getenv("AZURE_OPENAI_ENDPOINT"):
    from dotenv import load_dotenv
    load_dotenv(RAIZ / ".env")

from langchain_openai import AzureChatOpenAI
from deepeval.models.base_model import DeepEvalBaseLLM

DEPLOYMENT_GPT_LUNA = "gpt-5.6-luna"


def chat_gpt_luna(temperature: float = 0.0) -> AzureChatOpenAI:
    """
    LLM de LangChain apuntando al deployment de Azure gpt-5.6-luna, el mismo
    que usa el agente real de este proyecto cuando `AGENT_MODEL=azure`.

    `temperature` se ignora a proposito: gpt-5.6-luna es un modelo de
    razonamiento (familia "gpt-5" en adelante) y la API lo rechaza con 400 si
    se envia ese parametro (ver `app/llm.py`, `OPENAI_SIN_TEMPERATURE`). Por la
    misma razon se fija `reasoning_effort="none"`: sin eso, cualquier llamada
    con herramientas de funcion -- incluida la salida estructurada que usa
    `with_structured_output(method="function_calling")` -- falla con 400
    (`OPENAI_SIN_RAZONAMIENTO`, descubierto el 2026-09-08).
    """
    return AzureChatOpenAI(
        azure_deployment=DEPLOYMENT_GPT_LUNA,
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
        reasoning_effort="none",
        timeout=60,
        max_retries=2,
    )


class JuezGptLuna(DeepEvalBaseLLM):
    """Envoltorio de gpt-5.6-luna (Azure) para usarlo como juez en DeepEval."""

    def load_model(self):
        """Devuelve el modelo de chat configurado para el juez de DeepEval."""
        return chat_gpt_luna(temperature=0.0)

    def generate(self, prompt: str) -> str:
        """Invoca el juez sincronicamente y devuelve su texto."""
        return self.model.invoke(prompt).content

    async def a_generate(self, prompt: str) -> str:
        """Invoca el juez asincronicamente y devuelve su texto."""
        respuesta = await self.model.ainvoke(prompt)
        return respuesta.content

    def get_model_name(self) -> str:
        """Devuelve el nombre del modelo juez para identificar los reportes."""
        return f"{DEPLOYMENT_GPT_LUNA} (Azure OpenAI)"
