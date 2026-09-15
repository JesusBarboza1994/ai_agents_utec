"""Repository for `chats`: the main table -- one thread per chat_key, linked to its customer."""

import uuid
from datetime import datetime, timezone

from ..connection import connection


def get_or_create_chat(
    chat_key: str, customer_id: str, *,
    channel: str = "whatsapp", channel_number: str | None = None,
) -> str:
    """Existing chat id for `chat_key`, or a new row on first contact."""
    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM chats WHERE chat_key = %s", (chat_key,))
        row = cur.fetchone()
        if row:
            return row[0]

        now = datetime.now(timezone.utc)
        chat_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO chats (id, chat_key, customer_id, channel, channel_number, created_at, last_message_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (chat_id, chat_key, customer_id, channel, channel_number, now, now),
        )
        return chat_id


def touch(chat_id: str) -> None:
    """Bumps `last_message_at` -- called whenever a new message lands on the chat."""
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE chats SET last_message_at = %s WHERE id = %s",
            (datetime.now(timezone.utc), chat_id),
        )
