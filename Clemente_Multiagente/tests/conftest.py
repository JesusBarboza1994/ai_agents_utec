"""Configuracion comun de las pruebas: datos aislados, sin tocar los del equipo."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def servicio_reservas(tmp_path):
    from app.reservas.servicio_json import ServicioReservasJSON

    return ServicioReservasJSON(archivo_reservas=tmp_path / "reservas.json")


@pytest.fixture
def servicio_incidencias(tmp_path):
    from app.incidencias.servicio_json import ServicioIncidenciasJSON

    return ServicioIncidenciasJSON(archivo=tmp_path / "incidencias.json")
