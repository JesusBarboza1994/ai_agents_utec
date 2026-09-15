"""
Webchat controller (`GET /`, `POST /api/chat`, `POST /api/sesiones/<id>/reset`).

Not a real channel: WhatsApp is (see `whatsapp_controller.py`). This is the
only HTTP surface that calls the orchestrator synchronously, so it stays as
the integration point `tests/test_seguridad_reservas.py` and the demo UI
exercise -- removing it would also remove that coverage.
"""

import uuid

from flask import jsonify, render_template, request, session

from ...contratos import MensajeEntrante
from ..services import chat_service


def browser_session_id() -> str:
    """Opaque identity signed by Flask; never comes from the client's JSON."""
    if "clemente_sesion" not in session:
        session["clemente_sesion"] = f"web-{uuid.uuid4().hex}"
    return session["clemente_sesion"]


def chat_demo():
    browser_session_id()
    return render_template("chat.html")


def chat():
    data = request.get_json(silent=True) or {}
    text = (data.get("mensaje") or "").strip()
    if not text:
        return jsonify(error="El campo 'mensaje' es obligatorio"), 400

    session_id = browser_session_id()
    if data.get("sesion_id") and data["sesion_id"] != session_id:
        return jsonify(error="La sesión no pertenece a este navegador."), 403

    entrante = MensajeEntrante(
        sesion_id=session_id,
        texto=text,
        canal="webchat",
        nombre_cliente=data.get("nombre"),
        telefono=data.get("telefono"),
    )
    respuesta = chat_service.handle_incoming_message(entrante)

    return jsonify(
        respuesta=respuesta.texto,
        agente=respuesta.agente,
        motivo_ruta=respuesta.motivo_ruta,
        sesion_id=respuesta.sesion_id,
        escalado=respuesta.escalado,
    )


def reset(sesion_id: str):
    if sesion_id != session.get("clemente_sesion"):
        return jsonify(error="No autorizado"), 403
    chat_service.reset_session(sesion_id)
    return jsonify(estado="reiniciada", sesion_id=sesion_id)
