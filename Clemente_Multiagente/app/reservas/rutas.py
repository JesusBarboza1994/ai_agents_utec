"""
Blueprint de depuracion del Gestor de Reservas -- SOLO para probar
persistencia y rendimiento sin pasar por el LLM.

Por que existe: hoy la unica forma de ejercitar `crear_reserva` es via
`/api/chat`, que mezcla latencia de red/modelo con la latencia real de
Postgres (el `SELECT ... FOR UPDATE`), y ademas exige el intercambio
CONFIRMO <codigo> de `app/agentes/autorizacion.py`. Estas rutas llaman
`obtener_servicio()` directo, igual que hacen las tools del agente
(`app/agentes/tools/reservas_tools.py`) -- MISMA instancia, mismo backend
configurado por CLEMENTE_BACKEND_RESERVAS -- pero sin el agente ni la
confirmacion en el medio.

Registrado SOLO si CLEMENTE_DEBUG_ROUTES=1 (ver app/__init__.py). No tiene
autenticacion ni el flujo de propiedad-por-sesion de autorizacion.py: no
debe estar prendido nunca en un entorno con trafico real.
"""

from flask import Blueprint, jsonify, request

from . import obtener_servicio
from .validaciones import ReservaInvalida

bp = Blueprint("reservas_debug", __name__, url_prefix="/api/reservas")


@bp.post("")
def crear():
    """POST /api/reservas: crea una reserva validando y saneando el cuerpo; 400 si los datos son invalidos."""
    body = request.get_json(silent=True) or {}
    try:
        reserva = obtener_servicio().crear_reserva(
            nombre=body.get("nombre", ""),
            telefono=body.get("telefono", ""),
            fecha=body.get("fecha", ""),
            hora=body.get("hora", ""),
            personas=body.get("personas"),
            zona=body.get("zona", ""),
            notas=body.get("notas", ""),
        )
    except (ReservaInvalida, ValueError) as err:
        return jsonify(error=str(err)), 400
    return jsonify(reserva.__dict__), 201


@bp.get("/disponibilidad")
def disponibilidad():
    """GET /api/reservas/disponibilidad: lista opciones disponibles para fecha, hora, personas y zona dadas."""
    fecha = request.args.get("fecha", "")
    hora = request.args.get("hora", "")
    personas = request.args.get("personas", type=int)
    zona = request.args.get("zona") or None
    if not fecha or not hora or personas is None:
        return jsonify(error="fecha, hora y personas son obligatorios."), 400
    opciones = obtener_servicio().consultar_disponibilidad(fecha, hora, personas, zona)
    return jsonify([o.__dict__ for o in opciones])


@bp.get("/<reserva_id>")
def detalle(reserva_id):
    """GET /api/reservas/<id>: devuelve la reserva o 404 si no existe."""
    reserva = obtener_servicio().obtener_reserva(reserva_id)
    if reserva is None:
        return jsonify(error="Reserva no encontrada."), 404
    return jsonify(reserva.__dict__)


@bp.post("/<reserva_id>/cancelar")
def cancelar(reserva_id):
    """POST /api/reservas/<id>/cancelar: cancela la reserva o 404 si no existe."""
    reserva = obtener_servicio().cancelar_reserva(reserva_id)
    if reserva is None:
        return jsonify(error="Reserva no encontrada."), 404
    return jsonify(reserva.__dict__)


@bp.patch("/<reserva_id>")
def modificar(reserva_id):
    """PATCH /api/reservas/<id>: cambia fecha/hora/personas validando; 400 si son invalidas, 404 si no existe."""
    body = request.get_json(silent=True) or {}
    try:
        reserva = obtener_servicio().modificar_reserva(
            reserva_id,
            fecha=body.get("fecha"),
            hora=body.get("hora"),
            personas=body.get("personas"),
        )
    except (ReservaInvalida, ValueError) as err:
        return jsonify(error=str(err)), 400
    if reserva is None:
        return jsonify(error="Reserva no encontrada."), 404
    return jsonify(reserva.__dict__)
