"""
Channel-agnostic conversation flow.

Both functions here do I/O (Postgres, and later the LLM), so the adapter
calls both off the request thread -- the webhook acks before either runs
(see `whatsapp_controller`). Split in two anyway: `handle_incoming_message`
stores the customer's message and returns its chat_id (or None when there's
nothing to reply to); `generate_and_store_reply` is the separate, callable-
on-its-own step that turns a chat's session window into a stored reply. A
new channel only needs a controller + adapter service that translates its
own payload into an `IncomingMessage` and calls these two -- neither changes.
"""

from dataclasses import dataclass

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

    customer_id = customers_repository.get_or_create_customer(
        message.chat_key, first_name=message.sender_name, phone=message.sender_phone,
    )
    chat_id = chats_repository.get_or_create_chat(
        message.chat_key, customer_id,
        channel=message.channel, channel_number=message.channel_number,
    )
    messages_repository.append_message(
        chat_id, "user", message.text, provider_message_id=message.provider_message_id,
    )
    chats_repository.touch(chat_id)
    return chat_id


def digenerate_and_store_reply(chat_id: str, *, session_days: int) -> str:
    """
    The slow part: reads the session window, generates a reply and stores it.
    Meant to run off the request thread -- see `whatsapp_controller`.
    """
    recent = messages_repository.get_recent_messages(chat_id, session_days=session_days)
    reply = llm_bridge.generate_reply(recent)
    messages_repository.append_message(chat_id, "assistant", reply)
    chats_repository.touch(chat_id)
    return reply
