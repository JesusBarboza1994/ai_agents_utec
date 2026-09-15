"""Twilio WhatsApp webhook controller (`POST /api/webhook/whatsapp`)."""

import threading

from flask import Response, current_app, jsonify, request

from ...observabilidad.trazas import registrar
from ..services import message_service, outbound_whatsapp_service, whatsapp_service

# Twilio expects TwiML back; an empty <Response/> means "no automated reply".
_TWIML_ACK = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


def handle_webhook():
    """
    Signature validation is off on purpose (test project, not real Twilio
    traffic yet): `whatsapp_service.is_valid_request` is still there, tested
    and unused -- re-adding the check here is the only thing needed before
    this goes anywhere that gets real traffic.

    Only fast, in-memory work happens before the ack: the optional
    AccountSid check and building the IncomingMessage. Everything with I/O
    -- storing the message, the LLM call (mocked today, ~30s for real later)
    and Twilio's REST API to reply -- runs in a background thread, so none
    of it makes Twilio wait.
    """
    config = current_app.config["CLEMENTE"]
    if not config.database_url:
        return jsonify(error="Webhook not configured."), 503
    if not whatsapp_service.is_valid_account(request.form.get("AccountSid") or "", config.twilio_account_sid):
        return jsonify(error="Unexpected Twilio account"), 401

    message = whatsapp_service.parse_inbound(request.form)
    if message.chat_key:
        _process_in_background(message, session_days=config.chat_session_days)

    return Response(_TWIML_ACK, mimetype="text/xml")


def _process_in_background(message, *, session_days: int) -> None:
    """
    Off the request thread on purpose: storing the message, generating the
    reply and Twilio's REST API are all I/O the ack shouldn't wait on. Needs
    its own Flask app context -- `current_app` doesn't cross threads.

    Trade-off, on purpose: a storage failure here only gets traced, it can no
    longer turn into a 503 that makes Twilio retry delivery (the ack already
    went out). `provider_message_id` is kept on the message for a future
    dedup pass if that turns out to matter.
    """
    app = current_app._get_current_object()

    def _run() -> None:
        with app.app_context():
            config = app.config["CLEMENTE"]
            try:
                chat_id = message_service.handle_incoming_message(message, session_days=session_days)
                if not chat_id:
                    return
                reply = message_service.digenerate_and_store_reply(chat_id, session_days=session_days)
                outbound_whatsapp_service.send_whatsapp_message(
                    config.twilio_account_sid, config.twilio_auth_token,
                    config.twilio_whatsapp_from, message.chat_key, reply,
                )
            except Exception as error:
                registrar("error", message.chat_key, detalle={"error": f"whatsapp processing: {error}"})

    threading.Thread(target=_run, daemon=True).start()
