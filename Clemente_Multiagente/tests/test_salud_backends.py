"""
`/api/salud` expone los backends efectivos (paso 6 del plan: "hacer visible el backend").

Sin esto se podia desplegar creyendo que las incidencias iban a Trello o que
el estado de agentes vivia en Postgres cuando en realidad se escribia en un
archivo local del contenedor.
"""

from app import create_app
from app.config import Config


def test_salud_dice_en_que_backend_escribe_cada_modulo(monkeypatch):
    """Verifica que salud dice en que backend escribe cada modulo."""
    monkeypatch.setenv("RAG_BACKEND", "azure_search")
    cliente = create_app(Config(langsmith_tracing=False)).test_client()

    cuerpo = cliente.get("/api/salud").get_json()

    backends = cuerpo["backends"]
    assert backends["agentes"] == "local"
    assert backends["incidencias"] == "json"
    assert backends["rag"] == "azure_search"
    assert backends["guardrails_externos"] is False
    assert set(backends) >= {"reservas", "incidencias", "incidencias_mcp_url", "agentes", "rag", "datos_dir"}
