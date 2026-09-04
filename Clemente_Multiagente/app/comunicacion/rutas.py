"""
Capa de comunicacion -- responsable: Jesus.

Es la puerta de entrada del canal. Su trabajo es normalizar lo que llega
(WhatsApp via Twilio manda un formulario; el webchat manda JSON) a un
`MensajeEntrante`, pasarlo al orquestador y devolver la respuesta en el
formato que el canal espera.

El canal real acordado es **WhatsApp con Twilio**, y nada mas. El webchat
existe solo para desarrollar y demostrar sin depender de Twilio.

    GET  /                        -- webchat de demostracion
    POST /api/chat                -- API interna (la usa el webchat y las pruebas)
    POST /api/webhook/whatsapp    -- entrada de Twilio
    POST /api/sesiones/<id>/reset -- reinicia un hilo (util en la demo)
"""

import uuid

from flask import Blueprint, jsonify, render_template, request

from ..contratos import MensajeEntrante
from ..orquestador import responder as responder_orquestador
from .sesiones import limpiar_sesion, obtener_sesion

bp = Blueprint("comunicacion", __name__)


def _atender(entrante: MensajeEntrante):
    """Flujo unico: sesion -> orquestador -> sesion. Lo comparten todos los canales."""
    sesion = obtener_sesion(entrante.sesion_id, entrante.canal)
    if entrante.nombre_cliente:
        sesion.nombre_cliente = entrante.nombre_cliente
    if entrante.telefono:
        sesion.telefono = entrante.telefono

    respuesta = responder_orquestador(entrante, historial=sesion.historial)

    sesion.agregar("user", entrante.texto)
    sesion.agregar("assistant", respuesta.texto)
    sesion.ultimo_agente = respuesta.agente
    return respuesta


@bp.get("/")
def chat_demo():
    return render_template("chat.html")


@bp.post("/api/chat")
def chat():
    datos = request.get_json(silent=True) or {}
    texto = (datos.get("mensaje") or "").strip()
    if not texto:
        return jsonify(error="El campo 'mensaje' es obligatorio"), 400

    entrante = MensajeEntrante(
        sesion_id=datos.get("sesion_id") or f"web-{uuid.uuid4().hex[:8]}",
        texto=texto,
        canal=datos.get("canal", "webchat"),
        nombre_cliente=datos.get("nombre"),
        telefono=datos.get("telefono"),
    )
    respuesta = _atender(entrante)

    return jsonify(
        respuesta=respuesta.texto,
        agente=respuesta.agente,
        motivo_ruta=respuesta.motivo_ruta,
        sesion_id=respuesta.sesion_id,
        escalado=respuesta.escalado,
    )


@bp.post("/api/webhook/<canal>")
def webhook(canal: str):
    """
    Entrada del canal externo (`whatsapp`).

    Por ahora se acepta un formato generico de prueba. Jesus reemplaza
    `_normalizar` por el parseo real de Twilio, que envia un formulario
    (`application/x-www-form-urlencoded`) con `From` (ej. `whatsapp:+51999...`),
    `Body`, `ProfileName` y `MessageSid`.
    """
    datos = request.get_json(silent=True) or {}
    entrante = _normalizar(canal, datos)
    if entrante is None:
        return jsonify(error="Formato de webhook no reconocido"), 400

    respuesta = _atender(entrante)
    return jsonify(respuesta=respuesta.texto, agente=respuesta.agente)


def _normalizar(canal: str, datos: dict) -> MensajeEntrante | None:
    """Traduce el payload del canal al contrato interno."""
    texto = datos.get("mensaje") or datos.get("text") or datos.get("body") or datos.get("Body")
    remitente = (
        datos.get("from") or datos.get("From") or datos.get("sender") or datos.get("telefono")
    )
    if not texto or not remitente:
        return None

    return MensajeEntrante(
        sesion_id=f"{canal}-{remitente}",
        texto=str(texto).strip(),
        canal=canal,
        nombre_cliente=datos.get("nombre"),
        telefono=str(remitente),
    )


@bp.post("/api/sesiones/<sesion_id>/reset")
def reset(sesion_id: str):
    limpiar_sesion(sesion_id)
    return jsonify(estado="reiniciada", sesion_id=sesion_id)
