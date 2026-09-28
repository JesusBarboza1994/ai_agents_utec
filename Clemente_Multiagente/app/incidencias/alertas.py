"""Avisos de la capa de incidencias: errores legibles sin secretos y aviso cuando un reclamo no llega a Trello."""

import logging
import re

from ..observabilidad.trazas import registrar

log = logging.getLogger("clemente")

# Las librerias HTTP repiten en el mensaje de error la direccion completa que llamaron, y la de Trello
# lleva la clave y el token como parametros: se tapan antes de escribir el error en cualquier registro.
_SECRETO_EN_URL = re.compile(r"(key|token|secret)=[^&\s\"')]+", re.I)


def describir_error(error: Exception) -> str:
    """Texto corto del error para el registro, con la clave y el token de Trello tapados."""
    mensaje = _SECRETO_EN_URL.sub(r"\1=***", str(error))[:300]
    return f"{type(error).__name__}: {mensaje}"


# Reclamos de este proceso que recibieron codigo pero no tienen tarjeta. Se pierde al reiniciar; lo que queda
# para siempre es la linea ERROR del registro (Azure la guarda y se le puede poner una alerta).
_sin_tarjeta: list[str] = []


def avisar_sin_tarjeta(incidencia_id: str, sesion_id: str, error: Exception) -> None:
    """Deja el aviso donde el equipo lo pueda ver: linea ERROR, evento en las trazas y contador de /api/salud.

    El cliente ya recibio su codigo (el reclamo se guarda primero en el respaldo local), asi que este aviso
    es la unica pista de que el restaurante no vera esa tarjeta en Trello."""
    _sin_tarjeta.append(incidencia_id)
    log.error("incidencia %s NO llego a Trello (%s): el cliente recibio su codigo pero el equipo no vera la tarjeta",
              incidencia_id, describir_error(error))
    registrar("incidencia_sin_tarjeta", sesion_id, agente="incidencias",
              detalle={"incidencia": incidencia_id, "error": type(error).__name__})


def cantidad_sin_tarjeta() -> int:
    """Cuantos reclamos de este proceso recibieron codigo pero no llegaron a Trello."""
    return len(_sin_tarjeta)
