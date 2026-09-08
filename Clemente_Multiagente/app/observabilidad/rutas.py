"""
Endpoints de observabilidad. Los consume el panel interno y la demo final.

    GET /api/salud                -- el sistema esta arriba y con que modelo
    GET /api/trazas?sesion_id=..  -- ultimas trazas (que agente respondio y por que)
    GET /api/metricas             -- metricas agregadas para el informe
    GET /api/conversaciones       -- texto de los turnos registrados en disco
"""

from dataclasses import asdict

from flask import Blueprint, current_app, jsonify, request

from .trazas import leer_conversaciones, metricas, ultimas_trazas

bp = Blueprint("observabilidad", __name__, url_prefix="/api")


@bp.get("/salud")
def salud():
    config = current_app.config["CLEMENTE"]
    return jsonify(
        estado="ok" if not config.falta_credencial else "sin_credencial",
        proveedor=config.agent_model,
        modelo=config.modelo,
        embeddings=config.embeddings_backend,
        backend_reservas=config.backend_reservas,
        langsmith=config.langsmith_tracing,
        falta=config.falta_credencial or None,
    )


@bp.get("/trazas")
def trazas():
    limite = int(request.args.get("limite", 50))
    sesion_id = request.args.get("sesion_id")
    return jsonify([asdict(t) for t in ultimas_trazas(limite, sesion_id)])


@bp.get("/metricas")
def ver_metricas():
    return jsonify(metricas())


@bp.get("/conversaciones")
def conversaciones():
    """Turnos con su texto, tal como quedaron en disco. Sobreviven al reinicio."""
    limite = int(request.args.get("limite", 100))
    return jsonify(leer_conversaciones(limite, request.args.get("sesion_id")))
