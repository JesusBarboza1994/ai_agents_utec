"""
Canal de WhatsApp (Twilio): todo lo propio del proveedor, y nada mas.

Aqui viven la firma de la peticion, las direcciones `whatsapp:`, el BSUID y la
traduccion del formulario de Twilio al turno normalizado. El razonamiento y el
almacenamiento no son asunto de este modulo: `process_inbound` arma el
`MensajeEntrante` y se lo entrega a `chat_service.handle_incoming_message`, el
mismo flujo que usa el webchat -- alli se resuelven cliente, chat, historial,
seguridad y orquestador.

Un canal nuevo se agrega igual: un controller y un adaptador que traduzcan su
payload a `MensajeEntrante` + `IdentidadCanal`. No se duplica nada del flujo.
"""

from dataclasses import dataclass

import base64
import hashlib
import hmac
import re

from ...contratos import MensajeEntrante
from ...observabilidad.trazas import registrar
from . import chat_service

WHATSAPP_PREFIX = "whatsapp:"

# Business-scoped user id, e.g. "PE.2227643368025850": ISO country code, dot,
# alphanumerics. Twilio sends this instead of a real number when WhatsApp's
# privacy features mask the customer's phone.
_BSUID_PATTERN = re.compile(r"^[A-Za-z]{2}\.[A-Za-z0-9]+$")

# E.164 allows up to 15 digits; anything shorter than 7 is not a reachable number.
_E164_DIGITS_PATTERN = re.compile(r"^\d{7,15}$")


def is_valid_request(url: str, form: dict, signature: str, auth_token: str) -> bool:
    """
    Twilio's request validation: HMAC-SHA1 over the URL plus the sorted POST params.

    Assumes no query string on the webhook URL (Twilio folds query params into
    the same sorted list otherwise). Good enough for a plain POST endpoint.
    """
    if not signature or not auth_token:
        return False
    payload = url + "".join(f"{key}{form[key]}" for key in sorted(form))
    expected = base64.b64encode(
        hmac.new(auth_token.encode("utf-8"), payload.encode("utf-8"), hashlib.sha1).digest()
    ).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def is_valid_account(account_sid: str, expected_account_sid: str) -> bool:
    """
    Extra check beyond the signature: the message must come from our own
    Twilio account. Skipped (always valid) when `expected_account_sid` isn't
    configured, since it's optional today (only required for outbound).
    """
    if not expected_account_sid:
        return True
    return account_sid == expected_account_sid


def parse_whatsapp_address(address: str) -> str:
    """Strips the `whatsapp:` prefix and, for real numbers, the leading `+`."""
    without_prefix = (address or "").removeprefix(WHATSAPP_PREFIX)
    return without_prefix.removeprefix("+")


def is_business_scoped_user_id(chat_key: str) -> bool:
    """Reconoce identificadores de negocio de WhatsApp que sustituyen al telefono real."""
    return bool(_BSUID_PATTERN.match(chat_key))


def format_whatsapp_address(chat_key: str) -> str:
    """Rebuilds a Twilio address: business-scoped ids go without '+', numbers keep E.164."""
    if is_business_scoped_user_id(chat_key):
        return f"{WHATSAPP_PREFIX}{chat_key}"
    return f"{WHATSAPP_PREFIX}+{chat_key}"


def resolve_chat_key(form) -> str | None:
    """
    Identifier used for both the chat and the customer record: `From` without
    Twilio's prefix. Usually a phone number, but WhatsApp's privacy features
    can make Twilio send a business-scoped id instead -- either way it's
    stable across every message of the same chat, and it's what `To` must be
    rebuilt from when replying (see `format_whatsapp_address`).
    """
    return parse_whatsapp_address(form.get("From") or "") or None


def resolve_phone(form) -> str | None:
    """The real phone number, when the chat_key isn't a masked business-scoped id."""
    chat_key = resolve_chat_key(form)
    if chat_key and _E164_DIGITS_PATTERN.match(chat_key):
        return chat_key
    return None


def media_content_type(form) -> str | None:
    """MIME type of the first attachment, when the message carries media."""
    return form.get("MediaContentType0") or None


# --------------------------------------------------------------------------
# Entrada del canal: traducir y delegar
# --------------------------------------------------------------------------

@dataclass
class IncomingMessage:
    """El turno de WhatsApp ya traducido: lo que `parse_inbound` produce."""

    channel: str
    chat_key: str
    text: str
    sender_name: str | None = None
    sender_phone: str | None = None
    channel_number: str | None = None       # la direccion propia del negocio en el canal
    provider_message_id: str | None = None  # el id de Twilio para este mensaje (dedup futuro)
    unsupported_reason: str | None = None   # cuando no hay texto utilizable


def parse_inbound(form) -> IncomingMessage:
    """Translates Twilio's raw form payload into Clemente's channel-agnostic contract."""
    text = (form.get("Body") or "").strip()
    media_type = media_content_type(form)

    return IncomingMessage(
        channel="whatsapp",
        chat_key=resolve_chat_key(form) or "",
        text=text,
        sender_name=form.get("ProfileName") or None,
        sender_phone=resolve_phone(form),
        channel_number=parse_whatsapp_address(form.get("To") or "") or None,
        provider_message_id=form.get("MessageSid") or None,
        unsupported_reason=f"media sin manejar ({media_type})" if not text and media_type else None,
    )


def process_inbound(message: IncomingMessage) -> str | None:
    """Atiende un turno de WhatsApp y devuelve el texto que hay que responder.

    Devuelve None cuando no hay nada que contestar: sin `chat_key`, o un
    mensaje sin texto -- media que Clemente todavia no lee, que solo se traza.

    El `sesion_id` del hilo es estable entre mensajes (`whatsapp-<chat_key>`),
    porque de el cuelgan la propiedad de las reservas y las revisiones
    pendientes del orquestador.
    """
    if not message.chat_key:
        return None
    if not message.text:
        if message.unsupported_reason:
            registrar(
                "mensaje_no_soportado", message.chat_key,
                detalle={"motivo": message.unsupported_reason},
            )
        return None

    respuesta = chat_service.handle_incoming_message(
        MensajeEntrante(
            sesion_id=f"{message.channel}-{message.chat_key}",
            texto=message.text,
            canal=message.channel,
            nombre_cliente=message.sender_name,
            telefono=message.sender_phone,
        ),
        chat_service.IdentidadCanal(
            chat_key=message.chat_key,
            channel_number=message.channel_number,
            provider_message_id=message.provider_message_id,
        ),
    )
    return respuesta.texto
