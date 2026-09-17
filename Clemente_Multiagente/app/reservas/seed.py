"""
Sube el catalogo de mesas (`datos/mesas.json`) a Postgres.

Idempotente: usa `ON CONFLICT (id) DO UPDATE`, asi que correrlo de nuevo
tras editar `mesas.json` (nueva mesa, capacidad corregida) deja la tabla al
dia sin duplicar filas. `mesas.json` sigue siendo la unica fuente de verdad
sobre que mesas existen -- el agente no las inventa.

Uso:
    python -m app.reservas.seed
"""

import json
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

from ..db import migrate

CARPETA_DATOS = Path(__file__).parent / "datos"
ARCHIVO_MESAS = CARPETA_DATOS / "mesas.json"


def generar(database_url: str) -> int:
    """Aplica migraciones pendientes y sube el catalogo de mesas. Devuelve cuantas subio."""
    mesas = json.loads(ARCHIVO_MESAS.read_text(encoding="utf-8"))["mesas"]

    conn = psycopg2.connect(database_url)
    try:
        migrate.apply_pending(conn)
        with conn.cursor() as cur:
            for mesa in mesas:
                cur.execute(
                    "INSERT INTO mesas (id, zona, capacidad) VALUES (%s, %s, %s) "
                    "ON CONFLICT (id) DO UPDATE SET zona = EXCLUDED.zona, "
                    "capacidad = EXCLUDED.capacidad",
                    (mesa["id"], mesa["zona"], mesa["capacidad"]),
                )
        conn.commit()
    finally:
        conn.close()
    return len(mesas)


if __name__ == "__main__":
    load_dotenv()
    url = os.getenv("CLEMENTE_DATABASE_URL", "")
    if not url:
        raise SystemExit("CLEMENTE_DATABASE_URL no esta configurada")
    n = generar(url)
    print(f"OK: {n} mesas cargadas en {url.split('@')[-1]}")
