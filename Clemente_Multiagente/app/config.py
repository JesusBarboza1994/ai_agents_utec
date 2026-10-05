"""
Configuracion unica del proyecto, leida del entorno (.env).

Regla del equipo: ningun modulo lee `os.getenv` por su cuenta para decidir
comportamiento de negocio; todo pasa por aqui, para que se pueda ver de un
vistazo de que depende Clemente para arrancar.
"""

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent

load_dotenv(RAIZ / ".env")
_CLAVE_SESION_PROCESO = secrets.token_hex(32)


def _cloudinary_desde_entorno() -> tuple[str, str, str]:
    """(cloud_name, api_key, api_secret) leidos de CLOUDINARY_URL; vacios si no esta.

    CLOUDINARY_URL es el formato que entrega el panel de Cloudinary:
    `cloudinary://<api_key>:<api_secret>@<cloud_name>`."""
    url = urlparse(os.getenv("CLOUDINARY_URL", ""))
    if url.scheme != "cloudinary":
        return "", "", ""
    return url.hostname or "", unquote(url.username or ""), unquote(url.password or "")


@dataclass(frozen=True)
class Config:
    """Configuracion inmutable de Flask, modelos, seguridad, servicios y observabilidad.

    Sus valores describen la configuracion elegida; no prueban conectividad
    ni que un proveedor o validador este disponible."""
    secret_key: str = _CLAVE_SESION_PROCESO
    twilio_auth_token: str = ""
    twilio_account_sid: str = ""
    twilio_whatsapp_from: str = ""
    twilio_webhook_url: str = ""
    # Imagenes de WhatsApp: se re-suben a Cloudinary (ver media_service).
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""
    cloudinary_folder: str = "clemente/whatsapp"
    database_url: str = ""
    chat_session_days: int = 7
    hitl_token: str = ""
    guardrails_url: str = ""
    guardrails_token: str = ""
    guardrails_timeout: float = 3.0
    # LLM: por acuerdo del equipo, el razonamiento corre sobre API
    # (claude u openai). Ollama queda como respaldo sin conexion.
    agent_model: str = "openai"
    modelo: str = ""                       # ID concreto del modelo activo
    embeddings_backend: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    # RAG del catalogo: "chroma" (local, default) o "azure_search" (push directo
    # al indice de Azure AI Search, sin Blob Storage ni indexer -- ver
    # app/agentes/rag/indice.py).
    rag_backend: str = "chroma"

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
        if self.agent_model == "azure":
            if not os.getenv("AZURE_OPENAI_API_KEY"):
                return "AZURE_OPENAI_API_KEY"
            if not os.getenv("AZURE_OPENAI_ENDPOINT"):
                return "AZURE_OPENAI_ENDPOINT"
        if self.rag_backend == "azure_search":
            if not os.getenv("AZURE_SEARCH_ENDPOINT"):
                return "AZURE_SEARCH_ENDPOINT"
            if not os.getenv("AZURE_SEARCH_API_KEY"):
                return "AZURE_SEARCH_API_KEY"
        return ""

    @classmethod
    def desde_entorno(cls) -> "Config":
        """Construye Config a partir de variables de entorno y los valores predeterminados.

        Selecciona el modelo segun AGENT_MODEL y convierte timeout y banderas;
        un timeout no numerico produce ValueError. No comprueba credenciales remotas."""
        agent_model = os.getenv("AGENT_MODEL", "openai")
        cloud_name, cloud_key, cloud_secret = _cloudinary_desde_entorno()
        modelos = {
            "claude": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5"),
            "openai": os.getenv("OPENAI_MODEL", "gpt-5.6-terra"),
            "azure": os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5.6-luna"),
        }
        return cls(
            secret_key=os.getenv("CLEMENTE_SECRET_KEY") or _CLAVE_SESION_PROCESO,
            twilio_auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
            twilio_account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
            twilio_whatsapp_from=os.getenv("TWILIO_WHATSAPP_FROM", ""),
            twilio_webhook_url=os.getenv("TWILIO_WEBHOOK_URL", ""),
            cloudinary_cloud_name=cloud_name,
            cloudinary_api_key=cloud_key,
            cloudinary_api_secret=cloud_secret,
            database_url=os.getenv("CLEMENTE_DATABASE_URL", ""),
            chat_session_days=int(os.getenv("CLEMENTE_CHAT_SESSION_DAYS", "7")),
            hitl_token=os.getenv("CLEMENTE_HITL_TOKEN", ""),
            guardrails_url=os.getenv("CLEMENTE_GUARDRAILS_URL", ""),
            guardrails_token=os.getenv("CLEMENTE_GUARDRAILS_TOKEN", ""),
            guardrails_timeout=float(os.getenv("CLEMENTE_GUARDRAILS_TIMEOUT", "3")),
            agent_model=agent_model,
            modelo=modelos.get(agent_model, agent_model),
            embeddings_backend=os.getenv("EMBEDDINGS_BACKEND", "ollama"),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            rag_backend=os.getenv("RAG_BACKEND", "chroma"),
            backend_reservas=os.getenv("CLEMENTE_BACKEND_RESERVAS", "json"),
            langsmith_tracing=os.getenv("LANGSMITH_TRACING", "true").lower() == "true",
            langsmith_project=os.getenv("LANGSMITH_PROJECT", "clemente-grupo02"),
        )
