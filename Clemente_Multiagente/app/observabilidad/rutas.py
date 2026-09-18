"""
Endpoints de observabilidad. Los consume el panel interno y la demo final.

    GET /api/salud                -- el sistema esta arriba y con que modelo
    GET /api/trazas?sesion_id=..  -- ultimas trazas (que agente respondio y por que)
    GET /api/metricas             -- metricas agregadas para el informe
    GET /api/conversaciones       -- texto de los turnos registrados en disco
"""

from dataclasses import asdict

from flask import Blueprint, current_app, jsonify, request, session

from .trazas import leer_conversaciones, metricas, ultimas_trazas

bp = Blueprint("observabilidad", __name__, url_prefix="/api")


@bp.get("/salud")
def salud():
    """Devuelve configuracion activa y presencia de credencial, sin llamar a modelos o servicios.

    El estado ok indica esta comprobacion local, no una prueba integral de salud."""
    from ..agentes.almacen import backends_activos

    config = current_app.config["CLEMENTE"]
    return jsonify(
        estado="ok" if not config.falta_credencial else "sin_credencial",
        proveedor=config.agent_model,
        modelo=config.modelo,
        embeddings=config.embeddings_backend,
        backend_reservas=config.backend_reservas,
        # Backends efectivos (reservas, incidencias, estado de agentes, RAG):
        # para no desplegar creyendo que se escribe en Trello o Postgres
        # cuando en realidad se escribe en un archivo local.
        backends=backends_activos(),
        langsmith=config.langsmith_tracing,
        falta=config.falta_credencial or None,
    )


@bp.get("/trazas")
def trazas():
    """Devuelve trazas de la sesion del navegador hasta el limite solicitado.

    Una sesion ausente o ajena devuelve 403; limite se convierte a entero."""
    limite = int(request.args.get("limite", 50))
    sesion_id = session.get("clemente_sesion")
    if not sesion_id or request.args.get("sesion_id", sesion_id) != sesion_id:
        return jsonify(error="No autorizado"), 403
    return jsonify([asdict(t) for t in ultimas_trazas(limite, sesion_id)])


@bp.get("/metricas")
def ver_metricas():
    """Devuelve las metricas agregadas de las trazas conservadas en el proceso."""
    return jsonify(metricas())


@bp.get("/conversaciones")
def conversaciones():
    """Turnos con su texto, tal como quedaron en disco. Sobreviven al reinicio."""
    limite = int(request.args.get("limite", 100))
    sesion_id = session.get("clemente_sesion")
    if not sesion_id or request.args.get("sesion_id", sesion_id) != sesion_id:
        return jsonify(error="No autorizado"), 403
    return jsonify(leer_conversaciones(limite, sesion_id))
