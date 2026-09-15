"""Tests for the channel-agnostic conversation flow: no network, no Postgres."""

from app.communication.services import message_service
from app.communication.services.message_service import IncomingMessage
from app.observabilidad.trazas import ultimas_trazas


def _patch_repositories(monkeypatch, calls):
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
    calls = {}
    _patch_repositories(monkeypatch, calls)

    message = IncomingMessage(channel="whatsapp", chat_key="", text="hola")
    result = message_service.handle_incoming_message(message, session_days=7)

    assert result is None
    assert not calls


def test_handle_incoming_message_traces_unsupported_content_without_touching_the_db(monkeypatch):
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
    calls = {}
    _patch_repositories(monkeypatch, calls)

    message = IncomingMessage(channel="whatsapp", chat_key="51999111222", text="")
    result = message_service.handle_incoming_message(message, session_days=7)

    assert result is None
    assert not calls
    assert ultimas_trazas(10, "51999111222") == []


def test_generate_and_store_reply_stores_the_reply_and_returns_it(monkeypatch):
    calls = {}
    _patch_repositories(monkeypatch, calls)

    reply = message_service.digenerate_and_store_reply("chat-1", session_days=7)

    assert reply == "respuesta mockeada"
    assert calls["append"] == [("chat-1", "assistant", "respuesta mockeada", {})]
    assert calls["touch"] == "chat-1"
