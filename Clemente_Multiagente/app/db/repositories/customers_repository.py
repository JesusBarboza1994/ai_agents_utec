"""Repository for `customers`: one row per person we've talked to on any channel.

Dos clases de dato conviven en la fila: las columnas tipadas -- las que el
canal autentica (`chat_key`, `phone`) o pide explicitamente (`first_name`) --
y `data`, un jsonb sin tipar donde cae todo lo demas que se va sabiendo del
cliente. `get_customer` devuelve las dos mezcladas al mismo nivel, que es como
las consume quien arma el turno.
"""

import uuid
from datetime import datetime, timezone

from psycopg2.extras import Json

from ..connection import connection

# Columnas tipadas que `update_customer` sabe actualizar, en el orden del SET.
_CAMPOS_TIPADOS = ("first_name", "last_name", "phone")


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


def get_customer(chat_key: str) -> dict | None:
    """Ficha del cliente con el jsonb `data` desestructurado al mismo nivel, o None.

    La clave `data` no aparece en el resultado: ya viene desplegada. Ante una
    clave repetida gana la columna tipada -- `phone` es el numero con el que
    el canal lo autentico, no el que alguien dijo en una conversacion.
    """
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, chat_key, first_name, last_name, phone, data "
            "FROM customers WHERE chat_key = %s",
            (chat_key,),
        )
        row = cur.fetchone()
    if not row:
        return None

    customer_id, clave, first_name, last_name, phone, data = row
    return {
        **(data or {}),
        "id": customer_id, "chat_key": clave,
        "first_name": first_name, "last_name": last_name, "phone": phone,
    }


def update_customer(
    chat_key: str, *, first_name: str | None = None, last_name: str | None = None,
    phone: str | None = None, data: dict | None = None, reemplazar_data: bool = False,
) -> bool:
    """Actualiza la ficha del cliente: columnas tipadas y el jsonb `data` sin tipar.

    Solo toca lo que recibe -- un campo en None se queda como esta --, asi que
    dos llamadas que sepan cosas distintas del mismo cliente no se pisan. `data`
    se fusiona con lo guardado y las claves nuevas ganan; `reemplazar_data`
    sustituye el objeto entero, que es la unica forma de borrar una clave.

    Devuelve False si no habia nada que actualizar o el cliente no existe.
    """
    asignaciones: list[str] = []
    valores: list = []
    for columna, valor in zip(_CAMPOS_TIPADOS, (first_name, last_name, phone)):
        if valor is not None:
            asignaciones.append(f"{columna} = %s")
            valores.append(valor)
    if data is not None:
        asignaciones.append("data = %s::jsonb" if reemplazar_data else "data = data || %s::jsonb")
        valores.append(Json(data))
    if not asignaciones:
        return False

    asignaciones.append("updated_at = %s")
    valores.extend([datetime.now(timezone.utc), chat_key])
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"UPDATE customers SET {', '.join(asignaciones)} WHERE chat_key = %s",
            tuple(valores),
        )
        return cur.rowcount > 0
