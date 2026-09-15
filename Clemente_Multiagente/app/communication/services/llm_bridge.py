"""
Bridge from a chat's message window to the LLM conversation.

TODO: `generate_reply` is mocked -- it echoes the customer's last message
instead of calling the real orchestrator/LLM. That's the only thing that
needs to change; the round trip around it (store, reply, deliver via
`outbound_whatsapp_service`) is already real.
"""


def generate_reply(messages: list[dict]) -> str:
    """Mocked reply, so the WhatsApp round trip can be tested before the real model is wired."""
    last_user_text = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    return f"Recibimos tu mensaje: {last_user_text}"
