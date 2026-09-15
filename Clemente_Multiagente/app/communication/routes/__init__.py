"""
URL wiring for the communication blueprint. No business logic here: every
rule points straight at a controller function.

    GET  /                        -- webchat demo
    POST /api/chat                -- internal API (webchat + tests)
    POST /api/webhook/whatsapp    -- Twilio inbound
    POST /api/sesiones/<id>/reset -- resets a thread (handy for the demo)
"""

from flask import Blueprint

from ..controllers import chat_controller, whatsapp_controller

bp = Blueprint("communication", __name__)

bp.add_url_rule("/", view_func=chat_controller.chat_demo, methods=["GET"])
bp.add_url_rule("/api/chat", view_func=chat_controller.chat, methods=["POST"])
bp.add_url_rule("/api/webhook/whatsapp", view_func=whatsapp_controller.handle_webhook, methods=["POST"])
bp.add_url_rule("/api/sesiones/<sesion_id>/reset", view_func=chat_controller.reset, methods=["POST"])
