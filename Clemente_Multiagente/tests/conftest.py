"""Configuracion comun de las pruebas: datos aislados, sin tocar los del equipo."""

import sys
import os
from pathlib import Path

import pytest

# Antes de importar app/config: las pruebas no cargan credenciales del .env.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"
os.environ["DEEPTEAM_TELEMETRY_OPT_OUT"] = "YES"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def aislar_estado(tmp_path, monkeypatch):
    from app.agentes import autorizacion, memoria
    from app.observabilidad import trazas
    from app.orquestador import grafo
    from app.reservas import servicio_json as reservas
    from app.incidencias import servicio_json as incidencias
    from app.communication.services import sesiones
    import app.reservas
    import app.incidencias
    for clave in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "LANGSMITH_API_KEY", "TRELLO_API_KEY", "TRELLO_TOKEN", "TRELLO_MCP_URL"):
        monkeypatch.delenv(clave, raising=False)
    monkeypatch.setenv("CLEMENTE_BACKEND_INCIDENCIAS", "json")
    monkeypatch.setattr(autorizacion, "ARCHIVO", tmp_path / "autorizaciones.sqlite3")
    monkeypatch.setattr(memoria, "ARCHIVO", tmp_path / "clientes.json")
    monkeypatch.setattr(trazas, "ARCHIVO_CONVERSACIONES", tmp_path / "conversaciones.jsonl")
    monkeypatch.setattr(reservas, "ARCHIVO_RESERVAS", tmp_path / "reservas.json")
    monkeypatch.setattr(incidencias, "ARCHIVO", tmp_path / "incidencias.json")
    sesiones._sesiones.clear()
    app.reservas.reiniciar_servicio()
    app.incidencias.reiniciar_servicio()
    trazas._trazas.clear()
    grafo._escalado_de.clear()
    grafo.reiniciar_grafo()
    yield
    grafo.reiniciar_grafo()


@pytest.fixture(params=["json", "sqlite"])
def servicio_reservas(request, tmp_path):
    """Corre el contrato de ServicioReservas contra las dos implementaciones."""
    if request.param == "json":
        from app.reservas.servicio_json import ServicioReservasJSON

        return ServicioReservasJSON(archivo_reservas=tmp_path / "reservas.json")

    from app.reservas import seed
    from app.reservas.servicio_sqlite import ServicioReservasSQLite

    archivo_db = tmp_path / "clemente.db"
    seed.generar_en(archivo_db, con_ejemplos=False)
    return ServicioReservasSQLite(archivo_db=archivo_db)


@pytest.fixture
def servicio_incidencias(tmp_path):
    from app.incidencias.servicio_json import ServicioIncidenciasJSON

    return ServicioIncidenciasJSON(archivo=tmp_path / "incidencias.json")
