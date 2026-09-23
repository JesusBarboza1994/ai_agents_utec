"""
Contexto de la conversacion en curso: lo que el sistema ya sabe y el modelo no
deberia tener que repetir.

Historia de este archivo, que vale la pena conservar: la primera version usaba
un `ContextVar`. **No funciono**: LangChain ejecuta las tools en otro hilo y las
variables de contexto no cruzan hilos, asi que las tres incidencias de la prueba
del 2026-09-06 quedaron con `sesion_id: "desconocida"`. El mecanismo correcto en
LangChain 1.x es el contexto de `create_agent`: se declara con `context_schema=`,
se pasa en `agent.invoke(..., context=...)` y las tools lo reciben pidiendo un
parametro `runtime: ToolRuntime` -- que el modelo nunca ve.

Ademas del `sesion_id`, este contexto es el canal de vuelta de las tools hacia
el orquestador (idea de la guia de Jean): `escalado` y `datos` los escribe la
tool, y `grafo.py` los lee para armar el `RespuestaClemente` final.
"""

from typing import Any

from pydantic import BaseModel, Field


class ContextoConversacion(BaseModel):
    """Viaja del orquestador a las tools y vuelve con lo que ellas anotaron."""

    sesion_id: str = "desconocida"
    canal: str = "webchat"

    # --- lo que manda comunicacion, ya resuelto contra `customers` (Postgres) ---
    # `chat_key` explicito porque comunicacion no siempre lo puede derivar del
    # `sesion_id` como hace `chat_key_de` (webchat sin telefono, BSUID, etc.).
    # `cliente` es el dict que arma `customers_repository.get_customer`: columnas
    # tipadas (first_name, last_name, phone) y el jsonb `data` desestructurado al
    # mismo nivel. Vacio cuando el cliente es nuevo o el canal no lo mando.
    chat_key: str = ""
    cliente: dict[str, Any] = Field(default_factory=dict)

    # --- canal de vuelta: lo escriben las tools, lo lee el orquestador ---
    escalado: bool = False              # `escalar_a_staff` lo pone en True
    datos: dict[str, Any] = Field(default_factory=dict)   # reserva creada, incidencia, etc.


def telefono_de(sesion_id: str) -> str | None:
    """
    El telefono del cliente cuando el canal lo trae en el identificador de sesion.

    Con WhatsApp, la sesion es `whatsapp-51999111222`, asi que el telefono es un
    dato que el sistema ya tiene y no hace falta pedirlo de nuevo. En el webchat
    no hay telefono hasta que el cliente lo diga.
    """
    if sesion_id.startswith("whatsapp-"):
        return sesion_id.removeprefix("whatsapp-") or None
    return None


def chat_key_de(sesion_id: str) -> str | None:
    """
    El `chat_key` de Twilio (tabla `customers`), reconstruido del sesion_id.

    Misma extraccion que `telefono_de` -- WhatsApp arma la sesion como
    "whatsapp-<chat_key>" -- pero con el nombre correcto: el chat_key puede
    ser un telefono real o un id de negocio enmascarado (BSUID), y las tools
    que actualizan el perfil del cliente no deberian asumir que siempre es
    un numero.
    """
    return telefono_de(sesion_id)
