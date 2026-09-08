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
