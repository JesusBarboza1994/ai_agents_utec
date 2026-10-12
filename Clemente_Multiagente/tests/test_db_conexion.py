"""Pruebas del pool de conexiones ante conexiones que el servidor cierra por su cuenta."""

import os

import psycopg2
import pytest


@pytest.fixture
def contexto_postgres():
    """Empuja un app_context apuntando a la base de pruebas; se salta si no hay Postgres local."""
    database_url = os.getenv("CLEMENTE_DATABASE_URL", "")
    if not database_url:
        pytest.skip("CLEMENTE_DATABASE_URL no configurada: se salta el backend postgres")

    from app import create_app
    from app.config import Config

    app = create_app(Config(database_url=database_url))
    with app.app_context():
        yield database_url


def _cortar_conexiones_del_pool(database_url: str) -> None:
    """Simula al pooler cerrando conexiones inactivas: termina todo backend de la base salvo el propio."""
    admin = psycopg2.connect(database_url)
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = current_database() AND pid <> pg_backend_pid()"
            )
    finally:
        admin.close()


def test_conexion_cortada_por_el_servidor_se_reemplaza(contexto_postgres):
    """Verifica que una conexion cerrada por el servidor mientras esperaba en el pool no rompe la siguiente consulta."""
    from app.db.connection import connection

    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1")

    _cortar_conexiones_del_pool(contexto_postgres)

    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone() == (1,)


def test_conexion_rota_durante_la_consulta_no_vuelve_al_pool(contexto_postgres):
    """Verifica que si la conexion se cae en plena consulta, el pool no la reentrega a la siguiente peticion."""
    from app.db.connection import connection

    with pytest.raises(psycopg2.Error):
        with connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT pg_terminate_backend(pg_backend_pid())")

    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone() == (1,)
