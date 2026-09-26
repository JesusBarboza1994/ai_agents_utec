"""Comprobaciones al arrancar: avisan de configuraciones que no rompen nada a la vista pero fallan despues."""

import logging
import os

log = logging.getLogger("clemente")

AVISO_SIN_CLAVE_DE_SESION = (
    "Falta CLEMENTE_SECRET_KEY: Clemente usa una clave al azar y, cada vez que se reinicia, las sesiones del "
    "webchat se invalidan (el cliente deja de ser reconocido y no ve sus reservas). Definila en el .env con un "
    "texto largo aleatorio: python -c \"import secrets; print(secrets.token_hex(32))\""
)


def verificar_arranque(config) -> None:
    """Escribe en el registro un aviso por cada configuracion que falta y que solo se nota mas tarde."""
    if not os.getenv("CLEMENTE_SECRET_KEY"):
        log.warning(AVISO_SIN_CLAVE_DE_SESION)
