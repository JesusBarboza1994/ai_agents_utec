"""Repository for `customers`: one row per person we've talked to on any channel."""

import uuid
from datetime import datetime, timezone

from ..connection import connection


def get_or_create_customer(
    chat_key: str, *, first_name: str | None = None,
    last_name: str | None = None, phone: str | None = None,
) -> str:
    """Existing customer id for `chat_key`, or a new row on first contact."""
    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM customers WHERE chat_key = %s", (chat_key,))
        row = cur.fetchone()
        if row:
            return row[0]

        now = datetime.now(timezone.utc)
        customer_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO customers (id, chat_key, first_name, last_name, phone, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (customer_id, chat_key, first_name, last_name, phone, now, now),
        )
        return customer_id
