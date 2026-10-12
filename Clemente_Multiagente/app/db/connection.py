"""
Postgres connection pool.

`database_url` is read here, from the active Flask app's config, on every
call -- the only place in the whole db layer that touches it. Repositories
and services just call `connection()`, no config to thread through them.

Trade-off, on purpose: this ties `app/db/` to running inside a Flask app
context. Everything that touches Postgres today is a webhook controller, so
that's not a real cost; a future non-Flask caller (a worker, a script) would
need `with app.app_context():` around it, or this gets revisited then.
"""

import os
from contextlib import contextmanager
from threading import Lock

from flask import current_app

import psycopg2
import psycopg2.pool

from . import migrate

_pools: dict[str, psycopg2.pool.ThreadedConnectionPool] = {}
_pool_lock = Lock()


def _pool_for(database_url: str) -> psycopg2.pool.ThreadedConnectionPool:
    """Devuelve el pool cacheado para database_url, creandolo y migrando la base si es el primer uso."""
    with _pool_lock:
        if database_url not in _pools:
            # Threaded: el servidor corre con threaded=True y SimpleConnectionPool no es thread-safe.
            pool = psycopg2.pool.ThreadedConnectionPool(
                1, int(os.environ.get("CLEMENTE_DB_POOL_MAX", "5")), database_url,
                keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=3,
            )
            conn = pool.getconn()
            try:
                migrate.apply_pending(conn)
            finally:
                pool.putconn(conn)
            _pools[database_url] = pool
    return _pools[database_url]


def _conexion_viva(pool: psycopg2.pool.ThreadedConnectionPool):
    """Saca una conexion del pool y la descarta si el servidor ya la cerro (p. ej. por inactividad en el pooler)."""
    for _ in range(2):
        conn = pool.getconn()
        if not conn.closed:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                conn.rollback()
                return conn
            except psycopg2.Error:
                pass
        pool.putconn(conn, close=True)
    return pool.getconn()


@contextmanager
def connection():
    """Presta una conexion del pool; confirma al salir, revierte ante error y siempre devuelve la conexion."""
    database_url = current_app.config["CLEMENTE"].database_url
    if not database_url:
        raise RuntimeError("CLEMENTE_DATABASE_URL is not configured.")

    pool = _pool_for(database_url)
    conn = _conexion_viva(pool)
    try:
        yield conn
        conn.commit()
    except Exception:
        if not conn.closed:
            conn.rollback()
        raise
    finally:
        # Una conexion rota no vuelve al pool: la siguiente peticion recibe una nueva.
        pool.putconn(conn, close=bool(conn.closed))
