"""
Route-level tests for the Instagram OAuth relay callback.

Instagram's OAuth product only accepts a fixed HTTPS redirect_uri — a
client's own exp://.../mobile://... scheme can never be registered with
Meta directly. This endpoint is that fixed redirect_uri: Instagram lands
here, and this relays the result on to whatever URI the client packed into
`state` when it started the flow (see instagram_service.encode_app_redirect).
"""

from app.services import instagram_service


def test_callback_redirects_to_decoded_app_uri_with_code(client):
    state = instagram_service.encode_app_redirect("mobile://auth/instagram/callback")

    response = client.get(
        "/api/v1/auth/instagram/callback",
        params={"code": "abc123", "state": state},
        follow_redirects=False,
    )

    assert response.status_code in (302, 307)
    assert response.headers["location"] == "mobile://auth/instagram/callback?code=abc123"


def test_callback_forwards_error_when_instagram_denies_access(client):
    state = instagram_service.encode_app_redirect("exp://192.168.1.8:3000/--/auth/instagram/callback")

    response = client.get(
        "/api/v1/auth/instagram/callback",
        params={"error": "access_denied", "state": state},
        follow_redirects=False,
    )

    assert response.status_code in (302, 307)
    assert response.headers["location"] == (
        "exp://192.168.1.8:3000/--/auth/instagram/callback?error=access_denied"
    )


def test_callback_rejects_invalid_or_tampered_state(client):
    response = client.get(
        "/api/v1/auth/instagram/callback",
        params={"code": "abc123", "state": "not-a-real-state"},
    )

    assert response.status_code == 200
    assert "Invalid" in response.json()["detail"]


def test_callback_rejects_missing_state(client):
    response = client.get("/api/v1/auth/instagram/callback", params={"code": "abc123"})

    assert response.status_code == 200
    assert "Invalid" in response.json()["detail"]
