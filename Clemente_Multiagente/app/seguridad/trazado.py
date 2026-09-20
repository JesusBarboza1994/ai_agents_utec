"""
Redaccion de lo que viaja a LangSmith.

`registrar()` ya redacta las trazas propias, pero LangSmith traza por su cuenta
cada llamada al modelo y a cada tool: prompt completo (con la ficha del cliente),
argumentos de tools y salidas. Este modulo da un cliente de LangSmith que pasa
inputs y outputs por `redactar_pii` antes de enviarlos, usando la API publica
`tracing_context(client=...)`: vale para todo lo que corre dentro del `with`,
tambien las llamadas anidadas.

Limite: redacta los patrones que conoce `pii.py` (telefonos, correos, DNI,
tarjetas, secretos); no detecta nombres propios. La metadata de cada ejecucion
no pasa por aqui, por eso los ids de hilo del checkpoint no llevan el telefono.
"""

import os
from contextlib import nullcontext

from .pii import redactar_pii

_cliente = None


def ocultar(payload):
    """Funcion que LangSmith aplica a inputs y outputs de cada ejecucion antes de enviarlos."""
    try:
        return redactar_pii(payload)
    except Exception:
        return {"redactado": True}


def trazado_activo() -> bool:
    """True si LangSmith esta encendido y con clave (Observabilidad apaga el trazado si no hay clave)."""
    encendido = os.getenv("LANGSMITH_TRACING", "").lower() in ("true", "1")
    return encendido and bool(os.getenv("LANGSMITH_API_KEY"))


def contexto_de_trazado():
    """Context manager que redacta lo que se trace dentro de el; no hace nada con LangSmith apagado."""
    global _cliente
    if not trazado_activo():
        return nullcontext()
    from langsmith import Client, tracing_context

    if _cliente is None:
        _cliente = Client(hide_inputs=ocultar, hide_outputs=ocultar)
    return tracing_context(client=_cliente)
