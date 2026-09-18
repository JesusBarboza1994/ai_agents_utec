"""Configuracion comun de las pruebas: datos aislados, sin tocar los del equipo."""

import sys
import os
from pathlib import Path
from urllib.parse import urlparse

import pytest

# Antes de importar app/config: las pruebas no cargan credenciales del .env.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"
os.environ["DEEPTEAM_TELEMETRY_OPT_OUT"] = "YES"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HOSTS_LOCALES = {"localhost", "127.0.0.1", "::1"}


def url_postgres_de_pruebas() -> str:
    """URL de Postgres apta para pruebas DESTRUCTIVAS, o cadena vacia si no hay una segura.

    La suite aplica migraciones y borra `reservas`, asi que solo acepta
    CLEMENTE_TEST_DATABASE_URL o, a falta de ella, CLEMENTE_DATABASE_URL cuando
    apunta a localhost (el Postgres efimero del CI o de Docker). Una URL a la
    base compartida del equipo (Prisma) nunca llega a las pruebas, aunque
    este en el .env que `app.config` carga al importarse."""
    explicita = os.getenv("CLEMENTE_TEST_DATABASE_URL", "")
    if explicita:
        return explicita
    url = os.getenv("CLEMENTE_DATABASE_URL", "")
    if url and (urlparse(url).hostname or "") in HOSTS_LOCALES:
        return url
    return ""


@pytest.fixture(autouse=True)
def aislar_estado(tmp_path, monkeypatch):
    """Aisla archivos y registros globales por prueba y elimina credenciales del entorno.

    Usa tmp_path para autorizacion, memoria, trazas y revisiones; selecciona
    JSON y reinicia el grafo al entrar y salir, sin modificar datos del equipo.
    Deja en CLEMENTE_DATABASE_URL solo una URL local de pruebas, o la quita."""
    from app.agentes import almacen, autorizacion, memoria
    from app.observabilidad import trazas
    from app.orquestador import grafo
    from app.reservas import servicio_json as reservas
    from app.incidencias import servicio_json as incidencias
    from app.communication.services import sesiones
    import app.reservas
    import app.incidencias
    for clave in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "LANGSMITH_API_KEY", "TRELLO_API_KEY", "TRELLO_TOKEN", "TRELLO_MCP_URL"):
        monkeypatch.delenv(clave, raising=False)
    url_segura = url_postgres_de_pruebas()
    if url_segura:
        monkeypatch.setenv("CLEMENTE_DATABASE_URL", url_segura)
    else:
        monkeypatch.delenv("CLEMENTE_DATABASE_URL", raising=False)
    monkeypatch.setenv("CLEMENTE_BACKEND_INCIDENCIAS", "json")
    # Estado de agentes local y en memoria por defecto; `estado_postgres` lo cambia.
    monkeypatch.setenv("CLEMENTE_BACKEND_AGENTES", "local")
    monkeypatch.delenv("CLEMENTE_DATOS_DIR", raising=False)
    almacen.reiniciar_local()
    monkeypatch.setattr(autorizacion, "ARCHIVO", tmp_path / "autorizaciones.sqlite3")
    monkeypatch.setattr(memoria, "ARCHIVO", tmp_path / "clientes.json")
    monkeypatch.setattr(trazas, "ARCHIVO_CONVERSACIONES", tmp_path / "conversaciones.jsonl")
    monkeypatch.setattr(reservas, "ARCHIVO_RESERVAS", tmp_path / "reservas.json")
    monkeypatch.setattr(incidencias, "ARCHIVO", tmp_path / "incidencias.json")
    monkeypatch.setattr(grafo, "ARCHIVO_REVISIONES", tmp_path / "revisiones_hitl.json")
    sesiones._sesiones.clear()
    app.reservas.reiniciar_servicio()
    app.incidencias.reiniciar_servicio()
    trazas._trazas.clear()
    grafo._escalado_de.clear()
    grafo._revisiones.clear()
    grafo._revisiones_cargadas = True
    grafo.reiniciar_grafo()
    yield
    grafo.reiniciar_grafo()
    almacen.reiniciar_local()


@pytest.fixture
def estado_postgres(monkeypatch):
    """Estado de agentes en las tablas `agentes_*` del Postgres local de pruebas, con contexto Flask.

    Aplica migraciones, vacia esas tablas (solo las nuestras: no toca
    customers/chats/messages ni mesas/reservas) y deja abierto un
    `app_context()` porque el pool de `app/db` lo exige. Se salta sin base local."""
    database_url = url_postgres_de_pruebas()
    if not database_url:
        pytest.skip(
            "sin Postgres local de pruebas (CLEMENTE_TEST_DATABASE_URL, o "
            "CLEMENTE_DATABASE_URL en localhost): se salta el almacen postgres"
        )

    import psycopg2

    from app import create_app
    from app.config import Config
    from app.db import migrate

    conn = psycopg2.connect(database_url)
    try:
        migrate.apply_pending(conn)
        with conn.cursor() as cur:
            for tabla in ("agentes_propietarios", "agentes_propuestas", "agentes_perfiles",
                          "agentes_revisiones", "agentes_resoluciones", "agentes_continuidad",
                          "agentes_rechazos"):
                cur.execute(f"DELETE FROM {tabla}")
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("CLEMENTE_BACKEND_AGENTES", "postgres")
    app = create_app(Config(database_url=database_url, langsmith_tracing=False))
    ctx = app.app_context()
    ctx.push()
    yield app
    ctx.pop()


@pytest.fixture(params=["json", "postgres"])
def servicio_reservas(request, tmp_path):
    """Corre el contrato de ServicioReservas contra las dos implementaciones."""
    if request.param == "json":
        from app.reservas.servicio_json import ServicioReservasJSON

        return ServicioReservasJSON(archivo_reservas=tmp_path / "reservas.json")

    database_url = url_postgres_de_pruebas()
    if not database_url:
        pytest.skip(
            "sin Postgres local de pruebas (CLEMENTE_TEST_DATABASE_URL, o "
            "CLEMENTE_DATABASE_URL en localhost): se salta el backend postgres"
        )

    import psycopg2

    from app import create_app
    from app.config import Config
    from app.reservas import seed
    from app.reservas.servicio_postgres import ServicioReservasPostgres

    seed.generar(database_url)
    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM reservas")
        conn.commit()
    finally:
        conn.close()

    app = create_app(Config(database_url=database_url))
    ctx = app.app_context()
    ctx.push()
    request.addfinalizer(ctx.pop)
    return ServicioReservasPostgres()


@pytest.fixture
def servicio_incidencias(tmp_path):
    """Proporciona un gestor JSON de incidencias con archivo temporal exclusivo de la prueba."""
    from app.incidencias.servicio_json import ServicioIncidenciasJSON

    return ServicioIncidenciasJSON(archivo=tmp_path / "incidencias.json")
