"""Tests for the WhatsApp service: no network, no Postgres."""

import base64
import hashlib
import hmac

from app.communication.services.whatsapp_service import (
    format_whatsapp_address,
    is_business_scoped_user_id,
    is_valid_account,
    is_valid_request,
    media_content_type,
    parse_inbound,
    resolve_chat_key,
    resolve_phone,
)


def _signature(url: str, form: dict, token: str) -> str:
    payload = url + "".join(f"{k}{form[k]}" for k in sorted(form))
    return base64.b64encode(hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()).decode()


def test_is_valid_request_accepts_the_correct_signature():
    url = "https://clemente.example.com/api/webhook/whatsapp"
    form = {"From": "whatsapp:+51999111222", "Body": "hola"}
    signature = _signature(url, form, "shared-secret")
    assert is_valid_request(url, form, signature, "shared-secret")


def test_is_valid_request_rejects_wrong_signature_or_token():
    url = "https://clemente.example.com/api/webhook/whatsapp"
    form = {"From": "whatsapp:+51999111222", "Body": "hola"}
    signature = _signature(url, form, "shared-secret")
    assert not is_valid_request(url, form, signature, "other-token")
    assert not is_valid_request(url, form, "any-signature", "shared-secret")
    assert not is_valid_request(url, form, "", "shared-secret")


def test_resolve_chat_key_strips_the_whatsapp_prefix_and_plus():
    assert resolve_chat_key({"From": "whatsapp:+51999111222"}) == "51999111222"


def test_resolve_chat_key_keeps_a_business_scoped_id_as_is():
    # WhatsApp's privacy features make Twilio send this instead of a real number.
    assert resolve_chat_key({"From": "whatsapp:PE.2227643368025850"}) == "PE.2227643368025850"


def test_resolve_chat_key_is_none_without_from():
    assert resolve_chat_key({}) is None


def test_resolve_phone_returns_none_for_a_business_scoped_id():
    assert resolve_phone({"From": "whatsapp:PE.2227643368025850"}) is None


def test_resolve_phone_returns_the_number_when_its_real():
    assert resolve_phone({"From": "whatsapp:+51999111222"}) == "51999111222"


def test_is_business_scoped_user_id():
    assert is_business_scoped_user_id("PE.2227643368025850")
    assert not is_business_scoped_user_id("51999111222")


def test_format_whatsapp_address_keeps_e164_plus_for_real_numbers():
    assert format_whatsapp_address("51999111222") == "whatsapp:+51999111222"


def test_format_whatsapp_address_drops_plus_for_business_scoped_ids():
    assert format_whatsapp_address("PE.2227643368025850") == "whatsapp:PE.2227643368025850"


def test_media_content_type_reads_the_first_attachment():
    assert media_content_type({"MediaContentType0": "image/jpeg"}) == "image/jpeg"


def test_media_content_type_is_none_for_a_text_only_message():
    assert media_content_type({"Body": "hola"}) is None


def test_is_valid_account_skips_the_check_when_unconfigured():
    assert is_valid_account("ACanything", "")


def test_is_valid_account_matches_the_configured_account():
    assert is_valid_account("ACexpected", "ACexpected")
    assert not is_valid_account("ACother", "ACexpected")


def test_parse_inbound_builds_the_canonical_message():
    form = {
        "From": "whatsapp:+51999111222", "To": "whatsapp:+14155238886",
        "Body": " hola ", "ProfileName": "Ana", "MessageSid": "SM123",
    }
    message = parse_inbound(form)
    assert message.channel == "whatsapp"
    assert message.chat_key == "51999111222"
    assert message.text == "hola"
    assert message.sender_name == "Ana"
    assert message.sender_phone == "51999111222"
    assert message.channel_number == "14155238886"
    assert message.provider_message_id == "SM123"
    assert message.unsupported_reason is None


def test_parse_inbound_flags_media_without_body_as_unsupported():
    form = {"From": "whatsapp:+51999111222", "MediaContentType0": "image/jpeg"}
    message = parse_inbound(form)
    assert message.text == ""
    assert message.unsupported_reason and "image/jpeg" in message.unsupported_reason
