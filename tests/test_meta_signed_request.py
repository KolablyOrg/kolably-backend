"""
Unit tests for meta_signed_request — Meta's signed_request verification
format used by the Data Deletion Request Callback.
"""

import base64
import hashlib
import hmac
import json

import pytest

from app.core.meta_signed_request import InvalidSignedRequestError, parse_signed_request

SECRET = "test-app-secret"
OTHER_SECRET = "some-other-secret"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _make_signed_request(payload: dict, secret: str) -> str:
    payload_json = json.dumps(payload).encode()
    encoded_payload = _b64url(payload_json)
    signature = hmac.new(secret.encode(), encoded_payload.encode(), hashlib.sha256).digest()
    return f"{_b64url(signature)}.{encoded_payload}"


def test_parse_valid_signed_request_returns_payload():
    payload = {"algorithm": "HMAC-SHA256", "issued_at": 1234567890, "user_id": "17841441112302348"}
    signed_request = _make_signed_request(payload, SECRET)

    result = parse_signed_request(signed_request, secrets=[SECRET])

    assert result == payload


def test_parse_tries_each_secret_in_order():
    payload = {"algorithm": "HMAC-SHA256", "user_id": "999"}
    signed_request = _make_signed_request(payload, OTHER_SECRET)

    # First secret is wrong, second one matches — should still succeed
    result = parse_signed_request(signed_request, secrets=["wrong-secret", OTHER_SECRET])

    assert result["user_id"] == "999"


def test_parse_rejects_tampered_signature():
    payload = {"algorithm": "HMAC-SHA256", "user_id": "999"}
    signed_request = _make_signed_request(payload, SECRET)
    tampered = signed_request[:-1] + ("A" if signed_request[-1] != "A" else "B")

    with pytest.raises(InvalidSignedRequestError):
        parse_signed_request(tampered, secrets=[SECRET])


def test_parse_rejects_wrong_secret():
    payload = {"algorithm": "HMAC-SHA256", "user_id": "999"}
    signed_request = _make_signed_request(payload, SECRET)

    with pytest.raises(InvalidSignedRequestError):
        parse_signed_request(signed_request, secrets=["not-the-right-secret"])


def test_parse_rejects_unsupported_algorithm():
    payload = {"algorithm": "MD5", "user_id": "999"}
    signed_request = _make_signed_request(payload, SECRET)

    with pytest.raises(InvalidSignedRequestError):
        parse_signed_request(signed_request, secrets=[SECRET])


def test_parse_rejects_malformed_input():
    with pytest.raises(InvalidSignedRequestError):
        parse_signed_request("not-a-valid-signed-request", secrets=[SECRET])


def test_parse_skips_empty_secrets():
    payload = {"algorithm": "HMAC-SHA256", "user_id": "999"}
    signed_request = _make_signed_request(payload, SECRET)

    result = parse_signed_request(signed_request, secrets=["", SECRET])

    assert result["user_id"] == "999"
