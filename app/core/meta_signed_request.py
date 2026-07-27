"""
Verifies Meta's `signed_request` format — used for the Data Deletion Request
Callback (and historically the deauthorize callback). Format:

    <base64url-encoded HMAC-SHA256 signature>.<base64url-encoded JSON payload>

https://developers.facebook.com/docs/development/create-an-app/data-deletion-callback/
"""

import base64
import hashlib
import hmac
import json


class InvalidSignedRequestError(ValueError):
    pass


def _base64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def parse_signed_request(signed_request: str, secrets: list[str]) -> dict:
    """Verify and decode a `signed_request`, trying each secret in turn.

    Kolably's Meta app has two credentials — the parent app's (Facebook
    Login for Business, unused for OAuth) and the Instagram API product's.
    The Data Deletion Callback is configured once per parent app, so it's
    most likely signed with the parent secret, but this isn't documented
    precisely enough to bet on it — trying both is cheap and avoids
    silently rejecting genuine requests.
    """
    try:
        encoded_sig, payload = signed_request.split(".", 1)
    except ValueError:
        raise InvalidSignedRequestError("Malformed signed_request")

    try:
        signature = _base64url_decode(encoded_sig)
        data = json.loads(_base64url_decode(payload))
    except Exception as e:
        raise InvalidSignedRequestError(f"Could not decode signed_request: {e}")

    if str(data.get("algorithm", "")).upper() != "HMAC-SHA256":
        raise InvalidSignedRequestError(f"Unsupported algorithm: {data.get('algorithm')}")

    for secret in secrets:
        if not secret:
            continue
        expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
        if hmac.compare_digest(signature, expected):
            return data

    raise InvalidSignedRequestError("Signature verification failed against all known secrets")
