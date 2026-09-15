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

from contextlib import contextmanager

from flask import current_app

import psycopg2
import psycopg2.pool

from . import migrate

_pools: dict[str, psycopg2.pool.SimpleConnectionPool] = {}


def _pool_for(database_url: str) -> psycopg2.pool.SimpleConnectionPool:
    if database_url not in _pools:
        pool = psycopg2.pool.SimpleConnectionPool(1, 5, database_url)
        conn = pool.getconn()
        try:
            migrate.apply_pending(conn)
        finally:
            pool.putconn(conn)
        _pools[database_url] = pool
    return _pools[database_url]


@contextmanager
def connection():
    database_url = current_app.config["CLEMENTE"].database_url
    if not database_url:
        raise RuntimeError("CLEMENTE_DATABASE_URL is not configured.")

    pool = _pool_for(database_url)
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
