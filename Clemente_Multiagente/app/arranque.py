"""Comprobaciones al arrancar: avisan de configuraciones que no rompen nada a la vista pero fallan despues.

En local solo avisan. Con CLEMENTE_ENTORNO=produccion, si falta algo que en Azure se pierde o queda inseguro
en silencio, Clemente se niega a arrancar y dice exactamente que falta, en vez de funcionar a medias."""

import logging
import os

log = logging.getLogger("clemente")

AVISO_SIN_CLAVE_DE_SESION = (
    "Falta CLEMENTE_SECRET_KEY: Clemente usa una clave al azar y, cada vez que se reinicia, las sesiones del "
    "webchat se invalidan (el cliente deja de ser reconocido y no ve sus reservas). Definila en el .env con un "
    "texto largo aleatorio: python -c \"import secrets; print(secrets.token_hex(32))\""
)


class ConfiguracionDeProduccionInvalida(RuntimeError):
    """Falta configuracion que produccion necesita; el mensaje lista cada punto."""


def en_produccion() -> bool:
    """True si CLEMENTE_ENTORNO=produccion (la fija quien despliega en Azure; en local no se define)."""
    return os.getenv("CLEMENTE_ENTORNO", "").strip().lower() in {"produccion", "producción", "production", "prod"}


def problemas_de_produccion(config) -> list[str]:
    """Lo que impide arrancar en produccion: cada punto dice que falta y que pasaria si se deja asi."""
    from .incidencias import backend_activo

    problemas = []
    if not os.getenv("CLEMENTE_SECRET_KEY"):
        problemas.append("Falta CLEMENTE_SECRET_KEY: cada reinicio o cada replica invalidaria las sesiones del webchat.")
    if config.backend_reservas != "postgres":
        problemas.append(
            "CLEMENTE_BACKEND_RESERVAS debe ser 'postgres': con 'json' las reservas se guardan en un archivo "
            "y se pierden al reiniciar el contenedor.")
    if not config.database_url:
        problemas.append("Falta CLEMENTE_DATABASE_URL: sin ella no hay base de datos de reservas ni de clientes.")
    if not os.getenv("CLEMENTE_DATOS_DIR", "").strip():
        problemas.append(
            "Falta CLEMENTE_DATOS_DIR: quien es duena de cada reserva y las revisiones pendientes del equipo "
            "se guardarian dentro del contenedor y se perderian al reiniciar.")
    if not (config.guardrails_url and config.guardrails_token):
        problemas.append("Faltan CLEMENTE_GUARDRAILS_URL y CLEMENTE_GUARDRAILS_TOKEN: los mensajes no pasarian por Guardrails AI.")
    if backend_activo() == "json":
        problemas.append(
            "Los reclamos quedarian solo en un archivo del contenedor: faltan TRELLO_API_KEY y TRELLO_TOKEN "
            "(o CLEMENTE_BACKEND_INCIDENCIAS fuerza 'json').")
    if os.getenv("CLEMENTE_DEBUG_ROUTES") == "1":
        problemas.append("CLEMENTE_DEBUG_ROUTES=1 abre rutas de reservas sin autenticacion: no debe estar activo en produccion.")
    if config.falta_credencial:
        problemas.append(f"Falta {config.falta_credencial}: el agente no podria responder.")
    return problemas


def avisos_de_produccion(config) -> list[str]:
    """Lo que no impide arrancar pero conviene saber: se escribe como aviso."""
    avisos = []
    if os.getenv("CLEMENTE_GUARDRAILS_FALLA_CERRADA", "1") == "0":
        avisos.append(
            "CLEMENTE_GUARDRAILS_FALLA_CERRADA=0: si el servicio de Guardrails se cae, los mensajes pasan sin revisar.")
    if not config.twilio_auth_token:
        avisos.append("Falta TWILIO_AUTH_TOKEN: el webhook de WhatsApp no podra validar la firma de Twilio.")
    return avisos


def verificar_arranque(config) -> None:
    """Avisa en local; en produccion (CLEMENTE_ENTORNO=produccion) se niega a arrancar si falta configuracion."""
    if not en_produccion():
        if not os.getenv("CLEMENTE_SECRET_KEY"):
            log.warning(AVISO_SIN_CLAVE_DE_SESION)
        return
    for aviso in avisos_de_produccion(config):
        log.warning(aviso)
    problemas = problemas_de_produccion(config)
    if problemas:
        raise ConfiguracionDeProduccionInvalida(
            "Clemente no arranca en produccion (CLEMENTE_ENTORNO=produccion) porque falta configuracion:\n- "
            + "\n- ".join(problemas)
            + "\nDefinilas en la Container App y reinicia. En desarrollo local no definas CLEMENTE_ENTORNO.")
    log.info("Configuracion de produccion verificada")
