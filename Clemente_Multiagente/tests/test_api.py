"""
Pruebas de la capa HTTP, sin llamar al modelo.

Se reemplaza el orquestador por una funcion falsa: aqui se prueba el contrato
del canal (que entra, que sale), no la calidad de la respuesta del agente.
"""

import pytest

from app import create_app
from app.contratos import RespuestaClemente


@pytest.fixture
def cliente(monkeypatch):
    def orquestador_falso(entrante, historial=None):
        return RespuestaClemente(
            texto=f"eco: {entrante.texto}",
            agente="conocimiento",
            sesion_id=entrante.sesion_id,
            motivo_ruta="prueba",
        )

    monkeypatch.setattr(
        "app.comunicacion.rutas.responder_orquestador", orquestador_falso
    )
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_salud_reporta_proveedor_y_modelo(cliente):
    respuesta = cliente.get("/api/salud")
    datos = respuesta.get_json()
    assert respuesta.status_code == 200
    assert datos["estado"] in {"ok", "sin_credencial"}
    assert datos["proveedor"] and datos["modelo"]


def test_salud_avisa_cuando_falta_la_clave(monkeypatch):
    """Con el razonamiento sobre API, arrancar sin clave tiene que ser visible."""
    monkeypatch.setenv("AGENT_MODEL", "claude")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    datos = create_app().test_client().get("/api/salud").get_json()
    assert datos["estado"] == "sin_credencial"
    assert datos["falta"] == "ANTHROPIC_API_KEY"


def test_chat_devuelve_agente_y_sesion(cliente):
    respuesta = cliente.post("/api/chat", json={"mensaje": "hola", "sesion_id": "s1"})
    datos = respuesta.get_json()
    assert respuesta.status_code == 200
    assert datos["respuesta"] == "eco: hola"
    assert datos["agente"] == "conocimiento"
    assert datos["sesion_id"] == "s1"


def test_chat_sin_mensaje_es_error(cliente):
    assert cliente.post("/api/chat", json={}).status_code == 400


def test_webhook_normaliza_el_canal(cliente):
    respuesta = cliente.post(
        "/api/webhook/whatsapp", json={"from": "51999111222", "text": "hola"}
    )
    assert respuesta.status_code == 200
    assert respuesta.get_json()["respuesta"] == "eco: hola"


def test_el_historial_se_acumula_en_la_sesion(cliente):
    from app.comunicacion.sesiones import obtener_sesion

    cliente.post("/api/chat", json={"mensaje": "hola", "sesion_id": "s2"})
    cliente.post("/api/chat", json={"mensaje": "y el domingo?", "sesion_id": "s2"})
    assert len(obtener_sesion("s2").historial) == 4   # 2 turnos de cliente + 2 de Clemente


def test_langsmith_no_se_activa_sin_clave(monkeypatch):
    """Con el trazado pedido pero sin clave, se apaga y avisa: no falla en cada llamada."""
    import os

    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)

    create_app()
    assert os.environ["LANGSMITH_TRACING"] == "false"
