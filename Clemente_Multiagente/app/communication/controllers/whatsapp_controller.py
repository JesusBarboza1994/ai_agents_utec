"""Twilio WhatsApp webhook controller (`POST /api/webhook/whatsapp`)."""

import threading

from flask import Response, current_app, jsonify, request

from ...observabilidad.trazas import registrar
from ..services import outbound_whatsapp_service, whatsapp_service

# Twilio expects TwiML back; an empty <Response/> means "no automated reply".
_TWIML_ACK = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


def handle_webhook():
    """
    Verifica la firma de Twilio antes de aceptar la identidad del remitente.

    Only fast, in-memory work happens before the ack: the optional
    AccountSid check and building the IncomingMessage. Everything with I/O
    -- storing the message, the protected orchestrator call
    and Twilio's REST API to reply -- runs in a background thread, so none
    of it makes Twilio wait.
    """
    config = current_app.config["CLEMENTE"]
    if not config.database_url:
        return jsonify(error="Webhook not configured."), 503
    if not whatsapp_service.is_valid_account(request.form.get("AccountSid") or "", config.twilio_account_sid):
        return jsonify(error="Unexpected Twilio account"), 401

    if not whatsapp_service.is_valid_request(
        config.twilio_webhook_url or request.url,
        request.form, request.headers.get("X-Twilio-Signature", ""),
        config.twilio_auth_token,
    ):
        return jsonify(error="Invalid Twilio signature"), 401

    message = whatsapp_service.parse_inbound(request.form)
    if message.chat_key:
        _process_in_background(message)

    return Response(_TWIML_ACK, mimetype="text/xml")


def _process_in_background(message) -> None:
    """
    Off the request thread on purpose: storing the message, generating the
    reply and Twilio's REST API are all I/O the ack shouldn't wait on. Needs
    its own Flask app context -- `current_app` doesn't cross threads, y el
    flujo compartido lee de el la base y la ventana de historial.

    Trade-off, on purpose: a storage failure here only gets traced, it can no
    longer turn into a 503 that makes Twilio retry delivery (the ack already
    went out). `provider_message_id` is kept on the message for a future
    dedup pass if that turns out to matter.
    """
    app = current_app._get_current_object()

    def _run() -> None:
        """Procesa el turno protegido y envia la respuesta desde un contexto Flask independiente; registra errores sin contenido sensible."""
        with app.app_context():
            config = app.config["CLEMENTE"]
            try:
                reply = whatsapp_service.process_inbound(message)
                if reply is None:
                    return
                outbound_whatsapp_service.send_whatsapp_message(
                    config.twilio_account_sid, config.twilio_auth_token,
                    config.twilio_whatsapp_from, message.chat_key, reply,
                )
            except Exception as error:
                registrar("error", message.chat_key, detalle={"error": type(error).__name__})

    threading.Thread(target=_run, daemon=True).start()
