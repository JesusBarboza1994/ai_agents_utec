"""
Errores hacia afuera: solo el tipo, nunca el mensaje.

El texto de una excepcion puede traer la URL de Azure, el host de Postgres o el
cuerpo de una respuesta HTTP. Las trazas se leen desde /api/trazas y viajan a
LangSmith, y lo que una tool devuelve lo lee el modelo, que podria repetirselo
al cliente. Por eso ahi solo va el nombre de la excepcion; el detalle completo
queda en el log del servidor.
"""

import logging

from ..observabilidad.trazas import registrar
from .pii import redactar_pii

log = logging.getLogger("clemente")


def registrar_error(sesion_id: str, donde: str, error: Exception, agente: str = "") -> None:
    """Anota el error en la traza solo con su tipo y deja el detalle completo, redactado, en el log."""
    log.warning("%s (sesion %s): %s: %s", donde, sesion_id, type(error).__name__, redactar_pii(str(error)))
    registrar("error", sesion_id, agente=agente, detalle={"error": f"{donde}: {type(error).__name__}"})
