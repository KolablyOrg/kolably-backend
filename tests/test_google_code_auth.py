"""
Unit tests for auth_service.google_code_auth and the Google OAuth relay —
the authorization-code counterpart to google_auth, for clients without a
native Google Sign-In dev-client build (see google_oauth_service.py).

Mirrors tests/test_instagram_oauth_callback.py's relay-callback coverage and
delegates the actual sign-in/sign-up matrix to google_auth's own (already
exhaustive) tests in test_auth_service.py — this file only exercises the
code->id_token exchange and the wiring between the two.
"""

from app.schemas.auth import GoogleAuthRequest, GoogleCodeAuthRequest
from app.services import auth_service, google_oauth_service


async def test_google_code_auth_exchanges_code_then_delegates_to_google_auth(monkeypatch):
    captured = {}

    async def fake_exchange_code_for_id_token(code):
        captured["code"] = code
        return "id-token-from-google"

    async def fake_google_auth(data: GoogleAuthRequest, **kwargs):
        captured["google_auth_data"] = data
        return {"access_token": "tok", "user": {"id": "profile-1"}, "is_new_user": False}

    monkeypatch.setattr(google_oauth_service, "exchange_code_for_id_token", fake_exchange_code_for_id_token)
    monkeypatch.setattr(auth_service, "google_auth", fake_google_auth)

    result = await auth_service.google_code_auth(
        GoogleCodeAuthRequest(code="auth-code-123", role="business")
    )

    assert captured["code"] == "auth-code-123"
    assert captured["google_auth_data"].id_token == "id-token-from-google"
    assert captured["google_auth_data"].role == "business"
    assert result["access_token"] == "tok"


def test_callback_redirects_to_decoded_app_uri_with_code():
    state = google_oauth_service.encode_app_redirect("mobile://auth/google/callback")

    from fastapi.testclient import TestClient

    from app.main import app

    response = TestClient(app).get(
        "/api/v1/auth/google/callback",
        params={"code": "abc123", "state": state},
        follow_redirects=False,
    )

    assert response.status_code in (302, 307)
    assert response.headers["location"] == "mobile://auth/google/callback?code=abc123"


def test_callback_forwards_error_when_google_denies_access():
    state = google_oauth_service.encode_app_redirect(
        "exp://192.168.1.8:3000/--/auth/google/callback"
    )

    from fastapi.testclient import TestClient

    from app.main import app

    response = TestClient(app).get(
        "/api/v1/auth/google/callback",
        params={"error": "access_denied", "state": state},
        follow_redirects=False,
    )

    assert response.status_code in (302, 307)
    assert response.headers["location"] == (
        "exp://192.168.1.8:3000/--/auth/google/callback?error=access_denied"
    )


def test_callback_rejects_invalid_or_tampered_state():
    from fastapi.testclient import TestClient

    from app.main import app

    response = TestClient(app).get(
        "/api/v1/auth/google/callback",
        params={"code": "abc123", "state": "not-a-real-state"},
    )

    assert response.status_code == 200
    assert "Invalid" in response.json()["detail"]


def test_callback_rejects_missing_state():
    from fastapi.testclient import TestClient

    from app.main import app

    response = TestClient(app).get("/api/v1/auth/google/callback", params={"code": "abc123"})

    assert response.status_code == 200
    assert "Invalid" in response.json()["detail"]


def test_login_url_relays_through_fixed_callback_with_encoded_state():
    from urllib.parse import parse_qs, urlparse

    from fastapi.testclient import TestClient

    from app.main import app

    response = TestClient(app).get(
        "/api/v1/auth/google/login-url",
        params={"redirect_uri": "mobile://auth/google/callback"},
    )

    assert response.status_code == 200
    url = response.json()["url"]
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://accounts.google.com/o/oauth2/v2/auth"
    assert query["redirect_uri"][0] == google_oauth_service.relay_redirect_uri()
    assert (
        google_oauth_service.decode_app_redirect(query["state"][0])
        == "mobile://auth/google/callback"
    )
