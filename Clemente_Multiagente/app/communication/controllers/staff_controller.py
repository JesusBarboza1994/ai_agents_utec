"""Endpoints de revision humana con credencial exclusiva del personal."""
import secrets
from flask import current_app, request, jsonify

def _staff_autorizado() -> bool:
    """Comprueba el Bearer token del personal con comparacion constante.

    Devuelve False si CLEMENTE_HITL_TOKEN no esta configurado o no coincide."""
    token = current_app.config["CLEMENTE"].hitl_token
    recibido = request.headers.get("Authorization", "")
    return bool(token) and secrets.compare_digest(recibido, f"Bearer {token}")


def listar_revisiones():
    """Cola interna de decisiones; requiere un token distinto al webhook."""
    if not _staff_autorizado():
        return jsonify(error="No autorizado"), 401
    from ...orquestador.grafo import revisiones_pendientes
    return jsonify(revisiones=revisiones_pendientes())


def resolver_revision_staff(sesion_id: str):
    """Resuelve una revision HITL mediante POST autenticado del personal.

    Solo admite approve o reject (400); token incorrecto devuelve 401 y
    revision inexistente 404. Devuelve la respuesta para el cliente y datos
    de negocio; este endpoint no entrega por si mismo el mensaje por WhatsApp."""
    if not _staff_autorizado():
        return jsonify(error="No autorizado"), 401
    datos = request.get_json(silent=True) or {}
    decision = datos.get("decision", "")
    if decision not in {"approve", "reject"}:
        return jsonify(error="decision debe ser approve o reject"), 400
    from ...orquestador.grafo import resolver_revision
    try:
        respuesta = resolver_revision(sesion_id, decision, str(datos.get("motivo", "")))
    except KeyError as error:
        return jsonify(error=str(error)), 404
    return jsonify(
        estado="resuelta", decision=decision, sesion_id=sesion_id,
        respuesta_cliente=respuesta.texto, escalado=respuesta.escalado,
        datos=respuesta.datos,
    )
