"""Webhook de Trello (`HEAD` y `POST /api/webhook/trello`): avisa al cliente cuando una tarjeta pasa a Resuelto."""
from flask import Response, current_app, jsonify, request

from ...observabilidad.trazas import registrar
from ..services import cierre_trello_service


def verificar_webhook():
    """HEAD: Trello lo llama al registrar el webhook para comprobar que la URL responde; basta un 200."""
    return Response(status=200)


def recibir_webhook():
    """POST: acepta solo llamadas firmadas por Trello y avisa al cliente si la tarjeta paso a Resuelto.

    Responde 200 tambien cuando no hay nada que avisar o el envio falla: Trello reintenta ante un error
    y un reintento no arregla un WhatsApp rechazado. Una firma invalida o sin configurar devuelve 401."""
    config = current_app.config["CLEMENTE"]
    firma = request.headers.get("X-Trello-Webhook", "")
    if not cierre_trello_service.firma_valida(request.get_data(), config.trello_webhook_url, firma, config.trello_secret):
        registrar("webhook_rechazado", "trello", detalle={
            "motivo": "firma invalida o TRELLO_SECRET / TRELLO_WEBHOOK_URL sin configurar",
            "con_firma": bool(firma),
        })
        return jsonify(error="Invalid Trello signature"), 401

    carga = request.get_json(silent=True) or {}
    try:
        resultado = cierre_trello_service.avisar_cierre(carga)
    except Exception as error:
        registrar("error", "trello", detalle={"paso": "avisar_cierre", "error": type(error).__name__})
        resultado = {"estado": "error"}
    return jsonify(resultado), 200
