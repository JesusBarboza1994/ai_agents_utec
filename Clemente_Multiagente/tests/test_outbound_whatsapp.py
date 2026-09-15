"""Tests for the outbound WhatsApp service: no real network call."""

import pytest

from app.communication.services import outbound_whatsapp_service as service


class _FakeResponse:
    def __init__(self, status_code=201, payload=None):
        self.status_code = status_code
        self._payload = payload or {"sid": "SM123"}
        self.text = str(self._payload)

    def json(self):
        return self._payload


def test_send_whatsapp_message_addresses_a_real_number(monkeypatch):
    captured = {}

    def fake_post(url, auth, data, timeout):
        captured.update(url=url, auth=auth, data=data)
        return _FakeResponse()

    monkeypatch.setattr(service.requests, "post", fake_post)

    sid = service.send_whatsapp_message("AC123", "secret", "14155238886", "51999111222", "hola")

    assert sid == "SM123"
    assert captured["data"]["From"] == "whatsapp:+14155238886"
    assert captured["data"]["To"] == "whatsapp:+51999111222"
    assert captured["auth"] == ("AC123", "secret")


def test_send_whatsapp_message_addresses_a_business_scoped_id(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        service.requests, "post",
        lambda url, auth, data, timeout: captured.update(data=data) or _FakeResponse(),
    )

    service.send_whatsapp_message("AC123", "secret", "14155238886", "PE.2227643368025850", "hola")

    assert captured["data"]["To"] == "whatsapp:PE.2227643368025850"


def test_send_whatsapp_message_raises_without_credentials():
    with pytest.raises(service.WhatsAppSendError):
        service.send_whatsapp_message("", "", "", "51999111222", "hola")


def test_send_whatsapp_message_raises_on_twilio_error(monkeypatch):
    monkeypatch.setattr(
        service.requests, "post",
        lambda *a, **k: _FakeResponse(status_code=400, payload={"message": "invalid number"}),
    )
    with pytest.raises(service.WhatsAppSendError):
        service.send_whatsapp_message("AC123", "secret", "14155238886", "51999111222", "hola")
