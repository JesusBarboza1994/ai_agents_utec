"""Tests for the channel-agnostic conversation flow: no network, no Postgres."""

from app.communication.services import message_service
from app.communication.services.message_service import IncomingMessage
from app.observabilidad.trazas import ultimas_trazas


def _patch_repositories(monkeypatch, calls):
    """Sustituye repositorios y puente LLM por dobles que capturan llamadas sin red ni base real."""
    monkeypatch.setattr(
        "app.communication.services.message_service.customers_repository.get_or_create_customer",
        lambda chat_key, **k: calls.setdefault("customer", (chat_key, k)) and "customer-1",
    )
    monkeypatch.setattr(
        "app.communication.services.message_service.chats_repository.get_or_create_chat",
        lambda chat_key, customer_id, **k: calls.setdefault("chat", (chat_key, customer_id, k)) and "chat-1",
    )
    monkeypatch.setattr(
        "app.communication.services.message_service.chats_repository.touch",
        lambda chat_id: calls.setdefault("touch", chat_id),
    )
    monkeypatch.setattr(
        "app.communication.services.message_service.messages_repository.append_message",
        lambda chat_id, role, content, **k: calls.setdefault("append", []).append((chat_id, role, content, k)),
    )
    monkeypatch.setattr(
        "app.communication.services.message_service.messages_repository.get_recent_messages",
        lambda chat_id, **k: [{"role": "user", "content": "hola"}],
    )
    monkeypatch.setattr(
        "app.communication.services.message_service.llm_bridge.generate_reply",
        lambda messages: "respuesta mockeada",
    )


def test_handle_incoming_message_stores_the_message_and_returns_the_chat_id(monkeypatch):
    """Verifies handle incoming message stores the message and returns the chat id."""
    calls = {}
    _patch_repositories(monkeypatch, calls)

    message = IncomingMessage(
        channel="whatsapp", chat_key="51999111222", text="hola",
        sender_name="Ana", sender_phone="51999111222",
        channel_number="14155238886", provider_message_id="SM123",
    )
    result = message_service.handle_incoming_message(message, session_days=7)

    assert result == "chat-1"
    assert calls["customer"] == ("51999111222", {"first_name": "Ana", "phone": "51999111222"})
    assert calls["chat"] == ("51999111222", "customer-1", {"channel": "whatsapp", "channel_number": "14155238886"})
    assert calls["touch"] == "chat-1"
    assert calls["append"] == [("chat-1", "user", "hola", {"provider_message_id": "SM123"})]


def test_handle_incoming_message_skips_without_a_chat_key(monkeypatch):
    """Verifies handle incoming message skips without a chat key."""
    calls = {}
    _patch_repositories(monkeypatch, calls)

    message = IncomingMessage(channel="whatsapp", chat_key="", text="hola")
    result = message_service.handle_incoming_message(message, session_days=7)

    assert result is None
    assert not calls


def test_handle_incoming_message_traces_unsupported_content_without_touching_the_db(monkeypatch):
    """Verifies handle incoming message traces unsupported content without touching the db."""
    calls = {}
    _patch_repositories(monkeypatch, calls)

    message = IncomingMessage(
        channel="whatsapp", chat_key="51999111222", text="",
        unsupported_reason="media sin manejar (image/jpeg)",
    )
    result = message_service.handle_incoming_message(message, session_days=7)

    assert result is None
    assert not calls
    trazas = ultimas_trazas(10, "51999111222")
    assert len(trazas) == 1
    assert trazas[0].evento == "mensaje_no_soportado"
    assert trazas[0].detalle == {"motivo": "media sin manejar (image/jpeg)"}


def test_handle_incoming_message_skips_silently_without_text_or_reason(monkeypatch):
    """Verifies handle incoming message skips silently without text or reason."""
    calls = {}
    _patch_repositories(monkeypatch, calls)

    message = IncomingMessage(channel="whatsapp", chat_key="51999111222", text="")
    result = message_service.handle_incoming_message(message, session_days=7)

    assert result is None
    assert not calls
    assert ultimas_trazas(10, "51999111222") == []


def test_generate_and_store_reply_stores_the_reply_and_returns_it(monkeypatch):
    """Verifies generate and store reply stores the reply and returns it."""
    calls = {}
    _patch_repositories(monkeypatch, calls)

    reply = message_service.digenerate_and_store_reply("chat-1", session_days=7)

    assert reply == "respuesta mockeada"
    assert calls["append"] == [("chat-1", "assistant", "respuesta mockeada", {})]
    assert calls["touch"] == "chat-1"


def test_whatsapp_blocks_secrets_before_orchestrator_and_redacts_storage(monkeypatch):
    """El canal real bloquea tarjetas antes del agente y persiste solo texto redactado."""
    import pytest
    from app import create_app
    from app.config import Config
    calls = {}
    _patch_repositories(monkeypatch, calls)
    monkeypatch.setattr("app.communication.services.chat_service.responder_orquestador",
                        lambda *_args, **_kwargs: pytest.fail("Secreto enviado al agente"))
    app = create_app(Config(langsmith_tracing=False))
    with app.app_context():
        reply = message_service.process_incoming_message(
            IncomingMessage(channel="whatsapp", chat_key="51999111222",
                            text="mi tarjeta 4111111111111111"), session_days=7)
    assert "No env" in reply
    assert len(calls["append"]) == 2
    assert all("4111111111111111" not in row[2] for row in calls["append"])


def test_whatsapp_input_rejection_skips_agent_and_output_rejection_is_stored(monkeypatch):
    """Entrada rechazada evita el LLM; salida rechazada se sustituye antes de almacenar."""
    import pytest
    from app import create_app
    from app.config import Config
    from app.seguridad.guardrails_ai import ResultadoEntrada
    calls = {}
    _patch_repositories(monkeypatch, calls)
    monkeypatch.setattr("app.seguridad.guardrails_ai.validar_entrada",
                        lambda *_args: ResultadoEntrada(False, "ataque", "jailbreak"))
    monkeypatch.setattr("app.communication.services.chat_service.responder_orquestador",
                        lambda *_args, **_kwargs: pytest.fail("Entrada rechazada llego al LLM"))
    monkeypatch.setattr("app.seguridad.guardrails_ai.validar_salida",
                        lambda *_args: ResultadoEntrada(False, "salida peligrosa", "toxicidad"))
    with create_app(Config(langsmith_tracing=False)).app_context():
        reply = message_service.process_incoming_message(
            IncomingMessage(channel="whatsapp", chat_key="51999111222", text="ataque"), session_days=7)
    assert reply == "No puedo generar una respuesta apropiada en este momento."
    assert calls["append"][-1][2] == reply


def test_whatsapp_preserves_authenticated_identity_and_shared_history(monkeypatch):
    """El orquestador recibe la sesion estable y el historial redactado del canal real."""
    from app import create_app
    from app.config import Config
    from app.contratos import RespuestaClemente
    calls = {}
    _patch_repositories(monkeypatch, calls)
    monkeypatch.setattr(message_service.messages_repository, "get_recent_messages",
                        lambda *_args, **_kwargs: [
                            {"role": row[1], "content": row[2]} for row in calls.get("append", [])])
    received = []
    def responder(entrante, historial=None):
        """Captura identidad e historial y devuelve una respuesta sin usar un modelo."""
        received.append((entrante.sesion_id, list(historial)))
        return RespuestaClemente(texto="contacto persona@example.com", agente="informacion",
                                sesion_id=entrante.sesion_id, motivo_ruta="prueba")
    monkeypatch.setattr("app.communication.services.chat_service.responder_orquestador", responder)
    message = IncomingMessage(channel="whatsapp", chat_key="PE.ABC123", text="hola")
    with create_app(Config(langsmith_tracing=False)).app_context():
        message_service.process_incoming_message(message, session_days=7)
        reply = message_service.process_incoming_message(message, session_days=7)
    assert received[0][0] == "whatsapp-PE.ABC123"
    assert len(received[1][1]) == 2
    assert "persona@example.com" not in reply
    assert all("persona@example.com" not in row[2] for row in calls["append"])


def test_whatsapp_real_postgres_never_stores_raw_card(monkeypatch):
    """Con Postgres aislado disponible, persiste entrada bloqueada y salida sin tarjeta cruda."""
    import os, uuid, pytest
    from app import create_app
    from app.config import Config
    from app.communication.services.sesiones import limpiar_sesion
    if not os.getenv("CLEMENTE_DATABASE_URL"):
        pytest.skip("Requiere una base Postgres de pruebas aislada")
    monkeypatch.setattr("app.communication.services.chat_service.responder_orquestador",
                        lambda *_args, **_kwargs: pytest.fail("Tarjeta enviada al LLM"))
    key = "test-guardrails-" + uuid.uuid4().hex
    config = Config(database_url=os.environ["CLEMENTE_DATABASE_URL"], langsmith_tracing=False)
    with create_app(config).app_context():
        reply = message_service.process_incoming_message(IncomingMessage(
            channel="whatsapp", chat_key=key, text="mi tarjeta 4111111111111111"), session_days=7)
        chat_id = message_service._get_or_create_chat(IncomingMessage(channel="whatsapp", chat_key=key, text=""))
        rows = message_service.messages_repository.get_recent_messages(chat_id, session_days=7)
    assert len(rows) == 2
    assert rows[-1]["content"] == reply
    assert all("4111111111111111" not in row["content"] for row in rows)
    limpiar_sesion("whatsapp-" + key)
