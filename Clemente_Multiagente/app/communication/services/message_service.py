"""
Channel-agnostic conversation flow.

El flujo activo es process_incoming_message: restaura historial redactado de
Postgres, aplica chat_service (PII, entrada, orquestador, salida) y persiste
solo texto redactado antes del envio. Las funciones separadas y llm_bridge
se conservan como utilidades historicas para pruebas del almacenamiento.

Both legacy functions here do I/O (Postgres, and later the LLM), so the adapter
calls both off the request thread -- the webhook acks before either runs
(see `whatsapp_controller`). Split in two anyway: `handle_incoming_message`
stores the customer's message and returns its chat_id (or None when there's
nothing to reply to); `generate_and_store_reply` is the separate, callable-
on-its-own step that turns a chat's session window into a stored reply. A
new channel only needs a controller + adapter service that translates its
own payload into an `IncomingMessage` and calls these two -- neither changes.
"""

from dataclasses import dataclass

from ...seguridad.pii import redactar_pii
from ...contratos import MensajeEntrante
from . import chat_service
from .sesiones import MAXIMO_TURNOS

from ...db.repositories import chats_repository, customers_repository, messages_repository
from ...observabilidad.trazas import registrar
from . import llm_bridge


@dataclass
class IncomingMessage:
    """Canonical shape every channel adapter must produce."""

    channel: str
    chat_key: str
    text: str
    sender_name: str | None = None
    sender_phone: str | None = None
    channel_number: str | None = None       # the business's own address on this channel
    provider_message_id: str | None = None  # the channel's own id for this message (future dedup)
    unsupported_reason: str | None = None   # set by the adapter when there's no usable text


def _get_or_create_chat(message: IncomingMessage) -> str:
    """Resuelve cliente y chat sin guardar el contenido del mensaje entrante."""
    customer_id = customers_repository.get_or_create_customer(
        message.chat_key, first_name=message.sender_name, phone=message.sender_phone,
    )
    chat_id = chats_repository.get_or_create_chat(
        message.chat_key, customer_id,
        channel=message.channel, channel_number=message.channel_number,
    )
    return chat_id


def handle_incoming_message(message: IncomingMessage, *, session_days: int) -> str | None:
    """
    Stores the message against its customer/chat. Returns the chat_id, for
    `generate_and_store_reply` to use afterwards, or None when there's
    nothing to process -- no chat_key, or a media message Clemente can't
    read yet (only traced in that case, see `unsupported_reason`).
    """
    if not message.chat_key:
        return None
    if not message.text:
        if message.unsupported_reason:
            registrar("mensaje_no_soportado", message.chat_key, detalle={"motivo": message.unsupported_reason})
        return None

    chat_id = _get_or_create_chat(message)
    messages_repository.append_message(
        chat_id, "user", redactar_pii(message.text), provider_message_id=message.provider_message_id,
    )
    chats_repository.touch(chat_id)
    return chat_id


def digenerate_and_store_reply(chat_id: str, *, session_days: int) -> str:
    """
    Utilidad historica de pruebas: lee mensajes y ejecuta el puente simulado.
    No se usa desde el webhook; para trafico real usar process_incoming_message.
    Redacta el texto del puente antes de guardarlo.
    """
    recent = messages_repository.get_recent_messages(chat_id, session_days=session_days)
    reply = redactar_pii(llm_bridge.generate_reply(recent))
    messages_repository.append_message(chat_id, "assistant", reply)
    chats_repository.touch(chat_id)
    return reply


def process_incoming_message(message: IncomingMessage, *, session_days: int) -> str | None:
    """Aplica el flujo compartido antes de persistir texto redactado y devolverlo.

    Conserva la identidad autenticada de Twilio para autorizacion y HITL.
    El dato operativo original solo entra en el turno actual; el historial
    y los mensajes de Postgres reciben texto redactado. Restaura la ventana de historial de Postgres y no usa el puente simulado.
    """
    if not message.chat_key or not message.text:
        return None
    chat_id = _get_or_create_chat(message)
    sesion_id = f"{message.channel}-{message.chat_key}"
    sesion = chat_service.obtener_sesion(sesion_id, message.channel)
    recent = messages_repository.get_recent_messages(chat_id, session_days=session_days)
    sesion.historial = [
        {"role": row["role"], "content": redactar_pii(row["content"])}
        for row in recent
    ][-MAXIMO_TURNOS:]
    respuesta = chat_service.handle_incoming_message(MensajeEntrante(
        sesion_id=sesion_id, texto=message.text,
        canal=message.channel, nombre_cliente=message.sender_name,
        telefono=message.sender_phone,
    ))
    messages_repository.append_message(
        chat_id, "user", redactar_pii(message.text), provider_message_id=message.provider_message_id,
    )
    messages_repository.append_message(chat_id, "assistant", respuesta.texto)
    chats_repository.touch(chat_id)
    return respuesta.texto
