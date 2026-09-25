"""El flujo compartido de canal: mismo recorrido para webchat y WhatsApp, sin red ni Postgres."""

import os
import uuid

import pytest

from app import create_app
from app.config import Config
from app.contratos import MensajeEntrante, RespuestaClemente
from app.communication.services import chat_service, whatsapp_service
from app.communication.services.sesiones import limpiar_sesion, sesiones_activas
from app.communication.services.whatsapp_service import IncomingMessage
from app.observabilidad.trazas import ultimas_trazas

BASE_FALSA = "postgresql://prueba"


def _patch_repositories(monkeypatch, calls, recientes=None):
    """Sustituye los repositorios por dobles que capturan llamadas sin base real."""
    monkeypatch.setattr(
        "app.communication.services.chat_service.customers_repository.get_or_create_customer",
        lambda chat_key, **k: calls.setdefault("customer", (chat_key, k)) and "customer-1",
    )
    monkeypatch.setattr(
        "app.communication.services.chat_service.chats_repository.get_or_create_chat",
        lambda chat_key, customer_id, **k: calls.setdefault("chat", (chat_key, customer_id, k)) and "chat-1",
    )
    monkeypatch.setattr(
        "app.communication.services.chat_service.chats_repository.touch",
        lambda chat_id: calls.setdefault("touch", chat_id),
    )
    monkeypatch.setattr(
        "app.communication.services.chat_service.messages_repository.append_message",
        lambda chat_id, role, content, **k: calls.setdefault("append", []).append((chat_id, role, content, k)),
    )
    monkeypatch.setattr(
        "app.communication.services.chat_service.messages_repository.get_recent_messages",
        lambda chat_id, **k: list(recientes if recientes is not None else []),
    )


def _eco(entrante, historial=None, cliente=None, chat_key=None):
    """Orquestador falso: responde sin modelo y deja ver la sesion y el historial recibidos."""
    return RespuestaClemente(texto=f"eco: {entrante.texto}", agente="informacion",
                             sesion_id=entrante.sesion_id, motivo_ruta="prueba")


def _app(**kwargs):
    """App con base declarada y sin trazas remotas, para ejercitar la persistencia."""
    return create_app(Config(database_url=BASE_FALSA, langsmith_tracing=False, **kwargs))


def test_whatsapp_persiste_cliente_chat_y_mensajes(monkeypatch):
    """El canal real abre cliente y chat con su identidad y guarda los dos turnos."""
    calls = {}
    _patch_repositories(monkeypatch, calls)
    monkeypatch.setattr("app.communication.services.chat_service.responder_orquestador", _eco)

    message = IncomingMessage(
        channel="whatsapp", chat_key="51999111222", text="hola",
        sender_name="Ana", sender_phone="51999111222",
        channel_number="14155238886", provider_message_id="SM123",
    )
    with _app().app_context():
        reply = whatsapp_service.process_inbound(message)

    assert reply == "eco: hola"
    assert calls["customer"] == ("51999111222", {"first_name": "Ana", "phone": "51999111222"})
    assert calls["chat"] == ("51999111222", "customer-1",
                             {"channel": "whatsapp", "channel_number": "14155238886"})
    assert calls["append"] == [
        ("chat-1", "user", "hola", {"provider_message_id": "SM123"}),
        ("chat-1", "assistant", "eco: hola", {"provider_message_id": None}),
    ]
    assert calls["touch"] == "chat-1"


def test_webchat_recorre_el_mismo_flujo_y_persiste_igual(monkeypatch):
    """El webchat guarda en las mismas tablas; su chat_key es el sesion_id de la cookie."""
    calls = {}
    _patch_repositories(monkeypatch, calls)
    monkeypatch.setattr("app.communication.services.chat_service.responder_orquestador", _eco)

    with _app().app_context():
        respuesta = chat_service.handle_incoming_message(MensajeEntrante(
            sesion_id="web-abc123", texto="hola", canal="webchat", nombre_cliente="Ana"))

    assert respuesta.texto == "eco: hola"
    assert calls["customer"] == ("web-abc123", {"first_name": "Ana", "phone": None})
    assert calls["chat"] == ("web-abc123", "customer-1",
                             {"channel": "webchat", "channel_number": None})
    assert [fila[1] for fila in calls["append"]] == ["user", "assistant"]


def test_con_base_la_sesion_en_memoria_no_sobrevive_al_turno(monkeypatch):
    """Postgres es el almacen: la Sesion es andamio de un turno y se descarta."""
    calls = {}
    _patch_repositories(monkeypatch, calls)
    monkeypatch.setattr("app.communication.services.chat_service.responder_orquestador", _eco)

    with _app().app_context():
        chat_service.handle_incoming_message(MensajeEntrante(sesion_id="web-abc", texto="hola"))

    assert "web-abc" not in sesiones_activas()


def test_sin_base_configurada_el_historial_se_queda_en_memoria(monkeypatch):
    """Sin database_url no se toca ningun repositorio: la memoria es el unico respaldo."""
    calls = {}
    _patch_repositories(monkeypatch, calls)
    monkeypatch.setattr("app.communication.services.chat_service.responder_orquestador", _eco)

    with create_app(Config(langsmith_tracing=False)).app_context():
        chat_service.handle_incoming_message(MensajeEntrante(sesion_id="web-sinbase", texto="hola"))
    try:
        assert not calls
        assert "web-sinbase" in sesiones_activas()
    finally:
        limpiar_sesion("web-sinbase")


def test_un_fallo_de_la_base_no_deja_al_cliente_sin_respuesta(monkeypatch):
    """Si Postgres falla, el turno se responde desde memoria y el fallo queda trazado."""
    def explota(*_args, **_kwargs):
        """Simula una base inalcanzable."""
        raise RuntimeError("conexion rechazada")
    monkeypatch.setattr(
        "app.communication.services.chat_service.customers_repository.get_or_create_customer", explota)
    monkeypatch.setattr("app.communication.services.chat_service.responder_orquestador", _eco)

    with _app().app_context():
        respuesta = chat_service.handle_incoming_message(
            MensajeEntrante(sesion_id="web-falla", texto="hola"))
    try:
        assert respuesta.texto == "eco: hola"
        assert ultimas_trazas(5, "web-falla")[0].detalle["paso"] == "abrir_chat"
    finally:
        limpiar_sesion("web-falla")


def test_process_inbound_ignora_un_mensaje_sin_chat_key(monkeypatch):
    """Sin remitente no hay turno que atender ni fila que abrir."""
    calls = {}
    _patch_repositories(monkeypatch, calls)

    with _app().app_context():
        assert whatsapp_service.process_inbound(
            IncomingMessage(channel="whatsapp", chat_key="", text="hola")) is None
    assert not calls


def test_process_inbound_traza_media_sin_tocar_la_base(monkeypatch):
    """Un mensaje sin texto utilizable deja traza y no llega al flujo compartido."""
    calls = {}
    _patch_repositories(monkeypatch, calls)

    with _app().app_context():
        resultado = whatsapp_service.process_inbound(IncomingMessage(
            channel="whatsapp", chat_key="51999111222", text="",
            unsupported_reason="media sin manejar (image/jpeg)"))

    assert resultado is None
    assert not calls
    trazas = ultimas_trazas(10, "51999111222")
    assert len(trazas) == 1
    assert trazas[0].evento == "mensaje_no_soportado"
    assert trazas[0].detalle == {"motivo": "media sin manejar (image/jpeg)"}


def test_process_inbound_calla_sin_texto_ni_motivo(monkeypatch):
    """Un mensaje vacio sin motivo declarado no traza nada."""
    calls = {}
    _patch_repositories(monkeypatch, calls)

    with _app().app_context():
        assert whatsapp_service.process_inbound(
            IncomingMessage(channel="whatsapp", chat_key="51999111222", text="")) is None
    assert not calls
    assert ultimas_trazas(10, "51999111222") == []


def test_bloquea_secretos_antes_del_orquestador_y_persiste_redactado(monkeypatch):
    """El canal real bloquea tarjetas antes del agente y persiste solo texto redactado."""
    calls = {}
    _patch_repositories(monkeypatch, calls)
    monkeypatch.setattr("app.communication.services.chat_service.responder_orquestador",
                        lambda *_args, **_kwargs: pytest.fail("Secreto enviado al agente"))

    with _app().app_context():
        reply = whatsapp_service.process_inbound(IncomingMessage(
            channel="whatsapp", chat_key="51999111222", text="mi tarjeta 4111111111111111"))

    assert "No env" in reply
    assert len(calls["append"]) == 2
    assert all("4111111111111111" not in fila[2] for fila in calls["append"])


def test_entrada_rechazada_evita_el_llm_y_la_salida_sustituida_se_almacena(monkeypatch):
    """Entrada rechazada no llega al modelo; salida rechazada se sustituye antes de guardar."""
    from app.seguridad.guardrails_ai import ResultadoEntrada
    calls = {}
    _patch_repositories(monkeypatch, calls)
    monkeypatch.setattr("app.seguridad.guardrails_ai.validar_entrada",
                        lambda *_args: ResultadoEntrada(False, "ataque", "jailbreak"))
    monkeypatch.setattr("app.communication.services.chat_service.responder_orquestador",
                        lambda *_args, **_kwargs: pytest.fail("Entrada rechazada llego al LLM"))
    monkeypatch.setattr("app.seguridad.guardrails_ai.validar_salida",
                        lambda *_args: ResultadoEntrada(False, "salida peligrosa", "toxicidad"))

    with _app().app_context():
        reply = whatsapp_service.process_inbound(IncomingMessage(
            channel="whatsapp", chat_key="51999111222", text="ataque"))

    assert reply == "No puedo generar una respuesta apropiada en este momento."
    assert calls["append"][-1][2] == reply


def test_identidad_estable_e_historial_sin_repetir_el_mensaje_del_turno(monkeypatch):
    """El historial sale de la base, trae los turnos anteriores y va redactado.

    El mensaje que se esta atendiendo NO aparece en la ventana: ya viaja en
    `MensajeEntrante.texto` y el orquestador lo pone una sola vez en el prompt.
    """
    calls = {}
    almacenados = []
    _patch_repositories(monkeypatch, calls, recientes=almacenados)
    monkeypatch.setattr(
        "app.communication.services.chat_service.messages_repository.append_message",
        lambda chat_id, role, content, **k: almacenados.append({"role": role, "content": content}))

    recibido = []
    def responder(entrante, historial=None, cliente=None, chat_key=None):
        """Captura identidad e historial y responde con un correo, para comprobar la redaccion."""
        recibido.append((entrante.sesion_id, list(historial)))
        return RespuestaClemente(texto="contacto persona@example.com", agente="informacion",
                                 sesion_id=entrante.sesion_id, motivo_ruta="prueba")
    monkeypatch.setattr("app.communication.services.chat_service.responder_orquestador", responder)

    message = IncomingMessage(channel="whatsapp", chat_key="PE.ABC123", text="hola")
    with _app().app_context():
        whatsapp_service.process_inbound(message)
        reply = whatsapp_service.process_inbound(message)

    # Primer turno: nada previo. Segundo: los dos turnos ya guardados, y el
    # mensaje nuevo una sola vez, por `entrante.texto`.
    assert recibido[0] == ("whatsapp-PE.ABC123", [])
    assert [fila["role"] for fila in recibido[1][1]] == ["user", "assistant"]
    assert all(fila["content"] != "hola" for fila in recibido[0][1])
    assert "persona@example.com" not in reply
    assert all("persona@example.com" not in fila["content"] for fila in almacenados)


def test_postgres_real_nunca_guarda_la_tarjeta_cruda(monkeypatch):
    """Con Postgres aislado disponible, persiste entrada bloqueada y salida sin tarjeta cruda."""
    if not os.getenv("CLEMENTE_DATABASE_URL"):
        pytest.skip("Requiere una base Postgres de pruebas aislada")
    monkeypatch.setattr("app.communication.services.chat_service.responder_orquestador",
                        lambda *_args, **_kwargs: pytest.fail("Tarjeta enviada al LLM"))
    key = "test-guardrails-" + uuid.uuid4().hex
    config = Config(database_url=os.environ["CLEMENTE_DATABASE_URL"], langsmith_tracing=False)
    with create_app(config).app_context():
        reply = whatsapp_service.process_inbound(IncomingMessage(
            channel="whatsapp", chat_key=key, text="mi tarjeta 4111111111111111"))
        chat_id = chat_service._abrir_chat(
            MensajeEntrante(sesion_id="whatsapp-" + key, texto="", canal="whatsapp"),
            chat_service.IdentidadCanal(chat_key=key), key)
        rows = chat_service.messages_repository.get_recent_messages(chat_id, session_days=7)
    assert len(rows) == 2
    assert rows[-1]["content"] == reply
    assert all("4111111111111111" not in row["content"] for row in rows)
    limpiar_sesion("whatsapp-" + key)


def test_la_ficha_del_cliente_se_consulta_antes_de_llamar_al_orquestador(monkeypatch):
    """El turno lee lo guardado del cliente justo antes del LLM, con `data` desestructurado."""
    calls = {}
    _patch_repositories(monkeypatch, calls)
    consultas = []
    monkeypatch.setattr(
        "app.communication.services.chat_service.customers_repository.get_customer",
        lambda chat_key: consultas.append(chat_key) or {
            "id": "customer-1", "chat_key": chat_key, "first_name": "Ana",
            "last_name": None, "phone": "51999111222", "alergias": "mani",
        })
    monkeypatch.setattr("app.communication.services.chat_service.responder_orquestador", _eco)

    with _app().app_context():
        ficha = chat_service._ficha_del_cliente("51999111222", "whatsapp-51999111222")
        whatsapp_service.process_inbound(IncomingMessage(
            channel="whatsapp", chat_key="51999111222", text="hola"))

    assert consultas == ["51999111222", "51999111222"]
    assert ficha["alergias"] == "mani"          # viene del jsonb, al mismo nivel
    assert "data" not in ficha


def _orquestador_que_captura(recibido):
    """Orquestador falso que anota `cliente` y `chat_key` tal como los recibe."""
    def responder(entrante, historial=None, cliente=None, chat_key=None):
        """Guarda lo recibido y responde sin modelo."""
        recibido.update(cliente=cliente, chat_key=chat_key)
        return RespuestaClemente(texto="ok", agente="informacion",
                                 sesion_id=entrante.sesion_id, motivo_ruta="prueba")
    return responder


def test_whatsapp_le_pasa_la_ficha_y_el_chat_key_al_orquestador(monkeypatch):
    """La ficha leida de `customers` y el chat_key del canal llegan al orquestador en el turno."""
    calls, recibido = {}, {}
    _patch_repositories(monkeypatch, calls)
    ficha = {"id": "customer-1", "chat_key": "51999111222", "first_name": "Ana",
             "last_name": None, "phone": "51999111222", "alergias": "mani"}
    monkeypatch.setattr(
        "app.communication.services.chat_service.customers_repository.get_customer",
        lambda chat_key: ficha)
    monkeypatch.setattr("app.communication.services.chat_service.responder_orquestador",
                        _orquestador_que_captura(recibido))

    with _app().app_context():
        whatsapp_service.process_inbound(IncomingMessage(
            channel="whatsapp", chat_key="51999111222", text="hola"))

    assert recibido["cliente"] == ficha
    assert recibido["chat_key"] == "51999111222"


def test_webchat_usa_el_sesion_id_como_chat_key_ante_el_orquestador(monkeypatch):
    """Sin identidad de canal, el chat_key del webchat es su sesion_id, y la ficha viaja igual."""
    calls, recibido = {}, {}
    _patch_repositories(monkeypatch, calls)
    monkeypatch.setattr(
        "app.communication.services.chat_service.customers_repository.get_customer",
        lambda chat_key: None)
    monkeypatch.setattr("app.communication.services.chat_service.responder_orquestador",
                        _orquestador_que_captura(recibido))

    with _app().app_context():
        chat_service.handle_incoming_message(MensajeEntrante(sesion_id="web-ficha", texto="hola"))

    assert recibido["chat_key"] == "web-ficha"
    assert recibido["cliente"] == {}        # cliente nuevo: sin ficha, pero el argumento llega


def test_un_fallo_al_leer_el_cliente_no_corta_el_turno(monkeypatch):
    """Conocer al cliente mejora el turno; no poder leerlo no lo impide."""
    calls = {}
    _patch_repositories(monkeypatch, calls)
    def explota(*_args, **_kwargs):
        """Simula una consulta de cliente que falla."""
        raise RuntimeError("timeout")
    monkeypatch.setattr(
        "app.communication.services.chat_service.customers_repository.get_customer", explota)
    monkeypatch.setattr("app.communication.services.chat_service.responder_orquestador", _eco)

    with _app().app_context():
        reply = whatsapp_service.process_inbound(IncomingMessage(
            channel="whatsapp", chat_key="51999111222", text="hola"))
        assert reply == "eco: hola"
        assert ultimas_trazas(5, "whatsapp-51999111222")[0].detalle["paso"] == "leer_cliente"
