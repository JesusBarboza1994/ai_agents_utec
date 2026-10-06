"""
Repository for `messages`: every turn of a chat.

There is no stored "session" row and nothing expires in the background: the
7-day window the LLM sees is a runtime filter on `created_at`, computed fresh
on every read by `get_recent_messages`.
"""

from datetime import datetime, timedelta, timezone

from ..connection import connection

DEFAULT_SESSION_DAYS = 7

# Valores de `messages.type` (migracion 0006).
TYPE_TEXT = "text"
TYPE_IMAGE_URL = "image_url"   # `content` es la URL de Cloudinary de la imagen


def append_message(
    chat_id: str, role: str, content: str, *,
    provider_message_id: str | None = None, message_type: str = TYPE_TEXT,
) -> None:
    """Inserta un mensaje en Postgres; el llamador debe entregar contenido redactado."""
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO messages (chat_id, role, type, content, provider_message_id, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (chat_id, role, message_type, content, provider_message_id, datetime.now(timezone.utc)),
        )


def get_recent_messages(chat_id: str, *, session_days: int = DEFAULT_SESSION_DAYS) -> list[dict]:
    """The chat's messages from the last `session_days`, oldest first, each with its `type`."""
    since = datetime.now(timezone.utc) - timedelta(days=session_days)
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT role, type, content FROM messages WHERE chat_id = %s AND created_at >= %s "
            "ORDER BY created_at ASC, id ASC",
            (chat_id, since),
        )
        return [
            {"role": role, "type": message_type, "content": content}
            for role, message_type, content in cur.fetchall()
        ]
