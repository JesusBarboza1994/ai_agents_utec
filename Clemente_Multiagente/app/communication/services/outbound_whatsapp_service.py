"""
Sends outbound WhatsApp messages to customers via the Twilio REST API.

Deliberately separate from the inbound webhook: `whatsapp_controller` acks
Twilio immediately and never waits for the agent's reply. Once a reply is
ready -- today that means once `llm_bridge` actually calls the LLM -- this is
what delivers it back to the customer.
"""

import requests

from .whatsapp_service import format_whatsapp_address

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"


class WhatsAppSendError(RuntimeError):
    """Twilio rejected or failed to deliver an outbound message."""


def send_whatsapp_message(
    account_sid: str, auth_token: str, from_number: str, to_chat_key: str, body: str,
) -> str:
    """
    Sends `body` to `to_chat_key` via Twilio. Returns the outbound message SID.

    Same Account SID + Auth Token as the inbound webhook -- Twilio's own
    "for local testing" pattern, and it works fine in production too; an API
    key is a scoped, revocable alternative Twilio recommends but doesn't
    require (see `TWILIO_API_KEY_SID`/`SECRET` if that's ever worth adding).
    `to_chat_key` is the same identifier `resolve_chat_key` extracted from the
    inbound message (real phone or a business-scoped id): `format_whatsapp_address`
    rebuilds the right Twilio address for either shape, so no separate "real
    phone" is required to reply.
    """
    if not account_sid or not auth_token or not from_number:
        raise WhatsAppSendError("Twilio outbound credentials are not configured.")
    if not to_chat_key:
        raise WhatsAppSendError("No chat to reply to.")

    response = requests.post(
        f"{TWILIO_API_BASE}/Accounts/{account_sid}/Messages.json",
        auth=(account_sid, auth_token),
        data={
            "From": format_whatsapp_address(from_number),
            "To": format_whatsapp_address(to_chat_key),
            "Body": body,
        },
        timeout=10,
    )
    if response.status_code >= 400:
        raise WhatsAppSendError(f"Twilio rejected the message ({response.status_code}): {response.text}")
    return response.json().get("sid", "")
