"""Avisos de la capa de incidencias: errores legibles sin secretos y aviso cuando un reclamo no llega a Trello."""

import re

# Las librerias HTTP repiten en el mensaje de error la direccion completa que llamaron, y la de Trello
# lleva la clave y el token como parametros: se tapan antes de escribir el error en cualquier registro.
_SECRETO_EN_URL = re.compile(r"(key|token|secret)=[^&\s\"')]+", re.I)


def describir_error(error: Exception) -> str:
    """Texto corto del error para el registro, con la clave y el token de Trello tapados."""
    mensaje = _SECRETO_EN_URL.sub(r"\1=***", str(error))[:300]
    return f"{type(error).__name__}: {mensaje}"
