"""
Blueprint de solo lectura para el dashboard: lista los chats y sus mensajes.

Siempre registrado (ver app/__init__.py). No tiene autenticacion: expone
conversaciones y telefonos de clientes.
"""

from flask import Blueprint, jsonify

from ..db.connection import connection

bp = Blueprint("chats", __name__, url_prefix="/api/chats")


@bp.get("")
def listar():
    """GET /api/chats: chats con su cliente y ultimo mensaje, el mas reciente primero."""
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT c.id, c.chat_key, c.channel, c.last_message_at, "
            "cu.first_name, cu.last_name, cu.phone, "
            "(SELECT m.content FROM messages m WHERE m.chat_id = c.id "
            " ORDER BY m.created_at DESC, m.id DESC LIMIT 1), "
            "(SELECT m.type FROM messages m WHERE m.chat_id = c.id "
            " ORDER BY m.created_at DESC, m.id DESC LIMIT 1) "
            "FROM chats c JOIN customers cu ON cu.id = c.customer_id "
            "ORDER BY c.last_message_at DESC"
        )
        filas = cur.fetchall()
    return jsonify([
        {
            "id": id_, "chat_key": chat_key, "canal": canal,
            "ultimo_mensaje_en": ultimo_en.isoformat(),
            "nombre": " ".join(p for p in (nombre, apellido) if p) or None,
            "telefono": telefono,
            "ultimo_mensaje": {"image_url": "[imagen]", "audio_url": "[audio]"}.get(tipo, ultimo),
        }
        for id_, chat_key, canal, ultimo_en, nombre, apellido, telefono, ultimo, tipo in filas
    ])


@bp.get("/<chat_id>/mensajes")
def mensajes(chat_id):
    """GET /api/chats/<id>/mensajes: todos los mensajes del chat, del mas antiguo al mas nuevo.

    Un mensaje de audio llega con `tipo` "audio_url", la URL en `contenido` y su
    texto en `transcripcion` (null si la transcripcion fallo)."""
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, role, type, content, created_at, transcription FROM messages "
            "WHERE chat_id = %s ORDER BY created_at ASC, id ASC",
            (chat_id,),
        )
        filas = cur.fetchall()
    return jsonify([
        {"id": id_, "rol": rol, "tipo": tipo, "contenido": contenido,
         "creado": creado.isoformat(), "transcripcion": texto}
        for id_, rol, tipo, contenido, creado, texto in filas
    ])
