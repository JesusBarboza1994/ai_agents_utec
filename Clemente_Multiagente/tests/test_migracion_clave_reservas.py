"""
La migracion 0008 corrige la clave de idempotencia de las reservas que se modificaron antes del arreglo.

Solo corre con Postgres (CLEMENTE_DATABASE_URL de pruebas): la migracion es SQL y corre al arrancar la app,
asi que ademas de calcular la misma clave que Python no puede fallar si dos filas terminan con la misma.
"""
import os
from pathlib import Path

import pytest

from app.reservas.validaciones import clave_idempotencia

MIGRACION = Path(__file__).resolve().parents[1] / "app" / "db" / "migrations" / "0008_reservas_clave_tras_modificar.sql"
FECHA = "2026-12-04"


@pytest.fixture
def conexion():
    """Base de pruebas migrada y sin reservas; se salta sin Postgres."""
    database_url = os.getenv("CLEMENTE_DATABASE_URL", "")
    if not database_url:
        pytest.skip("CLEMENTE_DATABASE_URL no configurada: se salta la migracion de Postgres")
    import psycopg2

    from app.reservas import seed

    seed.generar(database_url)
    conn = psycopg2.connect(database_url)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM reservas")
    conn.commit()
    yield conn
    with conn.cursor() as cur:
        cur.execute("DELETE FROM reservas")
    conn.commit()
    conn.close()


def _insertar(conn, id_, telefono, hora, mesa, clave, creada, estado="modificada"):
    """Inserta una reserva con la clave que se le pase, como quedaron las modificadas antes del arreglo."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO reservas (id, nombre, telefono, fecha, hora, personas, mesa_id, estado, notas, creada, "
            "idempotency_key) VALUES (%s, 'Ana', %s, %s, %s, 2, %s, %s, '', %s, %s)",
            (id_, telefono, FECHA, hora, mesa, estado, creada, clave),
        )


def _claves(conn) -> dict[str, str]:
    """Clave actual de cada reserva."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, idempotency_key FROM reservas")
        return dict(cur.fetchall())


def test_la_migracion_deja_la_clave_que_calcula_python_y_no_falla_ante_un_duplicado(conexion):
    """Corrige la clave vieja, no toca la correcta y, si dos filas quedarian con la misma, no revienta."""
    # Movida de 20:00 a 21:00 con la clave de las 20:00: es el caso del 12-oct.
    _insertar(conexion, "R-MOVIDA", "999111222", "21:00", "M01", clave_idempotencia("999111222", FECHA, "20:00", 2),
              "2026-10-01T10:00:00")
    # Ya correcta: no se toca.
    correcta = clave_idempotencia("999333444", FECHA, "20:00", 2)
    _insertar(conexion, "R-BIEN", "999333444", "20:00", "M02", correcta, "2026-10-01T10:00:00", estado="confirmada")
    # Duplicado que ya existe: la creada despues con la clave nueva la conserva; la movida no puede tomarla.
    nueva_dup = clave_idempotencia("999555666", FECHA, "21:00", 2)
    _insertar(conexion, "R-DUP-VIEJA", "999555666", "21:00", "M03", clave_idempotencia("999555666", FECHA, "22:00", 2),
              "2026-10-01T10:00:00")
    _insertar(conexion, "R-DUP-NUEVA", "999555666", "21:00", "M04", nueva_dup, "2026-10-02T10:00:00",
              estado="confirmada")
    conexion.commit()

    with conexion.cursor() as cur:
        cur.execute(MIGRACION.read_text(encoding="utf-8"))
    conexion.commit()

    claves = _claves(conexion)
    assert claves["R-MOVIDA"] == clave_idempotencia("999111222", FECHA, "21:00", 2)
    assert claves["R-BIEN"] == correcta
    assert claves["R-DUP-NUEVA"] == nueva_dup
    assert claves["R-DUP-VIEJA"] == ""        # duplicado previo: queda sin clave, para revisarlo a mano


def test_la_migracion_se_puede_correr_dos_veces(conexion):
    """Una segunda pasada no cambia nada (la tabla temporal se borra al confirmar)."""
    _insertar(conexion, "R-MOVIDA", "999111222", "21:00", "M01", clave_idempotencia("999111222", FECHA, "20:00", 2),
              "2026-10-01T10:00:00")
    conexion.commit()
    for _ in range(2):
        with conexion.cursor() as cur:
            cur.execute(MIGRACION.read_text(encoding="utf-8"))
        conexion.commit()
    assert _claves(conexion)["R-MOVIDA"] == clave_idempotencia("999111222", FECHA, "21:00", 2)
