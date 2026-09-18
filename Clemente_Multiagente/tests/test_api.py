"""
Pruebas de la capa HTTP, sin llamar al modelo.

Se reemplaza el orquestador por una funcion falsa: aqui se prueba el contrato
del canal (que entra, que sale), no la calidad de la respuesta del agente.
"""

import threading

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
        "app.communication.services.chat_service.responder_orquestador", orquestador_falso
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


def _configure_whatsapp(cliente, token="test-token", database_url="postgresql://test"):
    from dataclasses import replace
    cliente.application.config["CLEMENTE"] = replace(
        cliente.application.config["CLEMENTE"], twilio_auth_token=token, database_url=database_url,
    )


class _ImmediateThread:
    """Test double for threading.Thread: runs the target synchronously, no real concurrency."""

    def __init__(self, target, daemon=True):
        self._target = target

    def start(self):
        self._target()


def test_whatsapp_webhook_acks_before_the_background_work_and_forwards_the_message(cliente, monkeypatch):
    # Signature validation is off (test project, see whatsapp_controller) --
    # no header needed here.
    _configure_whatsapp(cliente)
    form = {"From": "whatsapp:+51999111222", "WaId": "51999111222", "ProfileName": "Ana", "Body": "hola"}

    monkeypatch.setattr("app.communication.controllers.whatsapp_controller.threading.Thread", _ImmediateThread)
    received = {}
    monkeypatch.setattr(
        "app.communication.services.message_service.handle_incoming_message",
        lambda message, **k: received.update(
            channel=message.channel, chat_key=message.chat_key, text=message.text,
        ),
    )

    respuesta = cliente.post("/api/webhook/whatsapp", data=form)
    assert respuesta.status_code == 200
    assert b"<Response" in respuesta.data
    assert received == {"channel": "whatsapp", "chat_key": "51999111222", "text": "hola"}


def test_whatsapp_webhook_does_not_wait_for_the_background_work(cliente, monkeypatch):
    # Uses a real thread (no _ImmediateThread double) to prove the ack does
    # not block on it: a slow LLM call later shouldn't make Twilio wait.
    import time

    _configure_whatsapp(cliente)
    form = {"From": "whatsapp:+51999111222", "Body": "hola"}

    started = threading.Event()
    finished = threading.Event()

    def slow_handle_incoming_message(message, **k):
        started.set()
        time.sleep(0.2)
        finished.set()
        return None

    monkeypatch.setattr(
        "app.communication.services.message_service.handle_incoming_message", slow_handle_incoming_message,
    )

    start = time.monotonic()
    respuesta = cliente.post("/api/webhook/whatsapp", data=form)
    elapsed = time.monotonic() - start

    assert respuesta.status_code == 200
    assert elapsed < 0.1          # the ack didn't wait for the 0.2s background work
    assert not finished.is_set()  # background work was still running when the ack came back
    assert started.wait(timeout=1) and finished.wait(timeout=1)  # ...but it did run


def test_whatsapp_webhook_generates_and_sends_the_reply_in_background(cliente, monkeypatch):
    from dataclasses import replace

    _configure_whatsapp(cliente)
    cliente.application.config["CLEMENTE"] = replace(
        cliente.application.config["CLEMENTE"],
        twilio_account_sid="AC123", twilio_whatsapp_from="14155238886",
    )
    form = {"From": "whatsapp:+51999111222", "Body": "hola", "AccountSid": "AC123"}

    monkeypatch.setattr("app.communication.controllers.whatsapp_controller.threading.Thread", _ImmediateThread)
    monkeypatch.setattr(
        "app.communication.services.message_service.handle_incoming_message", lambda message, **k: "chat-1",
    )
    monkeypatch.setattr(
        "app.communication.services.message_service.digenerate_and_store_reply",
        lambda chat_id, **k: f"respuesta para {chat_id}",
    )
    sent = {}
    monkeypatch.setattr(
        "app.communication.services.outbound_whatsapp_service.send_whatsapp_message",
        lambda *args: sent.update(args=args),
    )

    respuesta = cliente.post("/api/webhook/whatsapp", data=form)
    assert respuesta.status_code == 200
    assert sent["args"] == ("AC123", "test-token", "14155238886", "51999111222", "respuesta para chat-1")


def test_whatsapp_webhook_does_not_reply_when_nothing_was_stored(cliente, monkeypatch):
    _configure_whatsapp(cliente)
    form = {"From": "whatsapp:+51999111222", "Body": "hola"}

    monkeypatch.setattr("app.communication.controllers.whatsapp_controller.threading.Thread", _ImmediateThread)
    monkeypatch.setattr(
        "app.communication.services.message_service.handle_incoming_message", lambda message, **k: None,
    )
    sent = []
    monkeypatch.setattr(
        "app.communication.services.outbound_whatsapp_service.send_whatsapp_message",
        lambda *args: sent.append(args),
    )

    respuesta = cliente.post("/api/webhook/whatsapp", data=form)
    assert respuesta.status_code == 200
    assert sent == []


def test_whatsapp_webhook_rejects_an_unexpected_twilio_account(cliente):
    _configure_whatsapp(cliente)
    from dataclasses import replace
    cliente.application.config["CLEMENTE"] = replace(
        cliente.application.config["CLEMENTE"], twilio_account_sid="ACexpected",
    )
    form = {"From": "whatsapp:+51999111222", "Body": "hola", "AccountSid": "ACother"}

    respuesta = cliente.post("/api/webhook/whatsapp", data=form)
    assert respuesta.status_code == 401


def test_whatsapp_webhook_traces_media_instead_of_dropping_it(cliente, monkeypatch):
    # Runs the real message_service (in the background, via _ImmediateThread
    # for a deterministic test): a media-only message returns before
    # touching Postgres, so no database is needed for this path.
    from app.observabilidad.trazas import ultimas_trazas

    _configure_whatsapp(cliente)
    monkeypatch.setattr("app.communication.controllers.whatsapp_controller.threading.Thread", _ImmediateThread)
    form = {
        "From": "whatsapp:+51999111222", "WaId": "51999111222",
        "MediaContentType0": "image/jpeg", "MediaUrl0": "https://api.twilio.com/media/ME123",
    }

    respuesta = cliente.post("/api/webhook/whatsapp", data=form)
    assert respuesta.status_code == 200
    assert b"<Response" in respuesta.data

    trazas = ultimas_trazas(10, "51999111222")
    assert len(trazas) == 1
    assert trazas[0].evento == "mensaje_no_soportado"
    assert "image/jpeg" in trazas[0].detalle["motivo"]


def test_el_historial_se_acumula_en_la_sesion(cliente):
    from app.communication.services.sesiones import obtener_sesion

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


def test_whatsapp_webhook_returns_503_when_unconfigured(cliente):
    assert cliente.post("/api/webhook/whatsapp", data={"Body": "hola"}).status_code == 503


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
