"""
Configuracion unica del proyecto, leida del entorno (.env).

Regla del equipo: ningun modulo lee `os.getenv` por su cuenta para decidir
comportamiento de negocio; todo pasa por aqui, para que se pueda ver de un
vistazo de que depende Clemente para arrancar.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent

load_dotenv(RAIZ / ".env")


@dataclass(frozen=True)
class Config:
    # LLM: por acuerdo del equipo, el razonamiento corre sobre API
    # (claude u openai). Ollama queda como respaldo sin conexion.
    agent_model: str = "claude"
    modelo: str = ""                       # ID concreto del modelo activo
    embeddings_backend: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"

    # Backends de datos
    backend_reservas: str = "json"

    # Observabilidad
    langsmith_tracing: bool = True
    langsmith_project: str = "clemente-grupo02"

    @property
    def falta_credencial(self) -> str:
        """Nombre de la variable de entorno que falta para poder llamar al modelo."""
        if self.agent_model == "claude" and not os.getenv("ANTHROPIC_API_KEY"):
            return "ANTHROPIC_API_KEY"
        if self.agent_model == "openai" and not os.getenv("OPENAI_API_KEY"):
            return "OPENAI_API_KEY"
        return ""

    @classmethod
    def desde_entorno(cls) -> "Config":
        agent_model = os.getenv("AGENT_MODEL", "claude")
        modelos = {
            "claude": os.getenv("ANTHROPIC_MODEL", "claude-opus-5"),
            "openai": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        }
        return cls(
            agent_model=agent_model,
            modelo=modelos.get(agent_model, agent_model),
            embeddings_backend=os.getenv("EMBEDDINGS_BACKEND", "ollama"),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            backend_reservas=os.getenv("CLEMENTE_BACKEND_RESERVAS", "json"),
            langsmith_tracing=os.getenv("LANGSMITH_TRACING", "true").lower() == "true",
            langsmith_project=os.getenv("LANGSMITH_PROJECT", "clemente-grupo02"),
        )
