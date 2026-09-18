"""
Redaccion de lo que viaja a LangSmith (A8 / paso 8 del plan del 18/09).

`registrar()` de observabilidad ya redacta las trazas propias, pero LangSmith
traza automaticamente cada llamada al modelo y a cada tool por fuera de ese
camino: prompt completo (con la ficha del cliente), argumentos de tools,
salidas y errores. Este modulo instala un cliente de LangSmith con
`hide_inputs`/`hide_outputs` que pasan por `redactar_pii` antes de enviar,
en el mismo punto donde LangChain toma su cliente (`get_cached_client`).

Limite honesto: redacta los patrones que `pii.py` conoce (telefonos, correos,
DNI, tarjetas, secretos); no detecta nombres propios ni todo dato sensible.
Si no se puede instalar el cliente (cambio interno de la libreria), cae a
`LANGSMITH_HIDE_INPUTS/OUTPUTS=true`, que oculta todo el contenido.
"""

import logging
import os
from typing import Any

from .pii import redactar_pii

log = logging.getLogger("clemente")


def ocultar(payload: Any) -> Any:
    """Funcion que LangSmith aplica a inputs y outputs de cada run antes de enviarlos."""
    try:
        return redactar_pii(payload)
    except Exception:
        # Ante un payload raro es preferible no enviar nada a enviarlo crudo.
        return {"redactado": True}


def cliente_redactado():
    """Cliente de LangSmith cuyos runs pasan por `ocultar` en entrada y salida."""
    from langsmith import Client

    return Client(hide_inputs=ocultar, hide_outputs=ocultar)


def activar_redaccion() -> str:
    """Instala el cliente redactado como el que usara LangChain; devuelve como quedo.

    "cliente": el cliente global de langsmith es el redactado (verificado).
    "env": no se pudo instalar y se activo LANGSMITH_HIDE_INPUTS/OUTPUTS.
    Idempotente: si ya esta instalado no crea otro."""
    try:
        import langsmith.run_trees as rt

        actual = getattr(rt, "_CLIENT", None)
        if actual is not None and getattr(actual, "_hide_inputs", None) is ocultar:
            return "cliente"
        cliente = cliente_redactado()
        with rt._LOCK:
            rt._CLIENT = cliente
        if rt.get_cached_client() is cliente:
            log.info("LangSmith: redaccion de PII activa en inputs y outputs de cada run")
            return "cliente"
    except Exception as error:
        log.warning("LangSmith: no se pudo instalar el cliente redactado (%s)", error)

    os.environ["LANGSMITH_HIDE_INPUTS"] = "true"
    os.environ["LANGSMITH_HIDE_OUTPUTS"] = "true"
    log.warning("LangSmith: se ocultan inputs y outputs completos (LANGSMITH_HIDE_*)")
    return "env"
