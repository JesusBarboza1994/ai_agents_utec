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
            agente="informacion",
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
    respuesta = cliente.post("/api/chat", json={"mensaje": "hola"})
    datos = respuesta.get_json()
    assert respuesta.status_code == 200
    assert datos["respuesta"] == "eco: hola"
    assert datos["agente"] == "informacion"
    assert datos["sesion_id"].startswith("web-")


def test_chat_sin_mensaje_es_error(cliente):
    assert cliente.post("/api/chat", json={}).status_code == 400


def test_webhook_normaliza_el_canal(cliente):
    from dataclasses import replace
    cliente.application.config["CLEMENTE"] = replace(cliente.application.config["CLEMENTE"], webhook_token="token-de-prueba")
    respuesta = cliente.post(
        "/api/webhook/whatsapp", json={"from": "51999111222", "text": "hola"},
        headers={"Authorization": "Bearer token-de-prueba"},
    )
    assert respuesta.status_code == 200
    assert respuesta.get_json()["respuesta"] == "eco: hola"


def test_el_historial_se_acumula_en_la_sesion(cliente):
    from app.comunicacion.sesiones import obtener_sesion

    sid = cliente.post("/api/chat", json={"mensaje": "hola"}).get_json()["sesion_id"]
    cliente.post("/api/chat", json={"mensaje": "y el domingo?", "sesion_id": sid})
    assert len(obtener_sesion(sid).historial) == 4   # 2 turnos de cliente + 2 de Clemente


def test_otro_navegador_no_puede_suplantar_leer_o_resetear(cliente):
    sid = cliente.post("/api/chat", json={"mensaje": "hola"}).get_json()["sesion_id"]
    otro = cliente.application.test_client()
    assert otro.post("/api/chat", json={"mensaje": "hola", "sesion_id": sid}).status_code == 403
    assert otro.post(f"/api/sesiones/{sid}/reset").status_code == 403
    assert otro.get(f"/api/trazas?sesion_id={sid}").status_code == 403
    assert otro.get(f"/api/conversaciones?sesion_id={sid}").status_code == 403


def test_webhook_sin_autenticacion_no_acepta_identidad(cliente):
    assert cliente.post("/api/webhook/whatsapp", json={"from": "900000001", "text": "hola"}).status_code == 503
    from dataclasses import replace
    cliente.application.config["CLEMENTE"] = replace(cliente.application.config["CLEMENTE"], webhook_token="secreto-de-prueba")
    assert cliente.post("/api/webhook/whatsapp", json={"from": "900000001", "text": "hola"}).status_code == 401


def test_las_conversaciones_solo_devuelven_el_hilo_propio(cliente):
    from app.observabilidad.trazas import registrar_conversacion
    sid = cliente.post("/api/chat", json={"mensaje": "hola"}).get_json()["sesion_id"]
    for sesion_id, texto in ((sid, "propio"), ("otro", "privado")):
        registrar_conversacion(sesion_id=sesion_id, mensaje=texto, respuesta="ok", agente="informacion", canal="webchat", motivo_ruta="test", duracion_ms=0)
    filas = cliente.get("/api/conversaciones").get_json()
    assert [f["mensaje"] for f in filas] == ["propio"]


def test_langsmith_no_se_activa_sin_clave(monkeypatch):
    """Con el trazado pedido pero sin clave, se apaga y avisa: no falla en cada llamada."""
    import os

    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)

    create_app()
    assert os.environ["LANGSMITH_TRACING"] == "false"


def test_la_conversacion_queda_registrada_en_disco(tmp_path, monkeypatch):
    """El texto de cada turno sobrevive al reinicio del servidor y a LangSmith caido."""
    from app.observabilidad import trazas

    monkeypatch.setattr(trazas, "ARCHIVO_CONVERSACIONES", tmp_path / "conversaciones.jsonl")

    trazas.registrar_conversacion(
        sesion_id="whatsapp-51999", mensaje="¿tienen estacionamiento?",
        respuesta="Sí, con convenio en Av. Grau 410.", agente="informacion",
        canal="whatsapp", motivo_ruta="pide un dato general", duracion_ms=1234.5,
    )

    turnos = trazas.leer_conversaciones()
    assert len(turnos) == 1
    assert turnos[0]["mensaje"] == "¿tienen estacionamiento?"
    assert turnos[0]["agente"] == "informacion"
    assert turnos[0]["canal"] == "whatsapp"
