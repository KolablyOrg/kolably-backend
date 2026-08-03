"""
Google OAuth authorization-code relay for mobile clients without a native
Google Sign-In dev-client build (plain Expo Go).

Google's "Web application" OAuth client type only accepts https/localhost
redirect_uris, so a mobile app's own exp://.../mobile://... scheme can never
be registered with Google directly — same constraint as Instagram (see
instagram_service.py) and solved the same way: this backend owns the one
fixed HTTPS redirect_uri and relays the result back to the caller's real
destination.
"""

from urllib.parse import urlencode

import httpx
from cryptography.fernet import InvalidToken

from app.core.config import settings
from app.core.crypto import decrypt_token, encrypt_token
from app.core.exceptions import ExternalServiceError

_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_SCOPES = "openid email profile"


def relay_redirect_uri() -> str:
    """The single, fixed HTTPS redirect_uri every relayed Google OAuth flow
    uses — Google rejects anything else for this client type. This backend
    relays the result on to the caller's real destination (see
    `encode_app_redirect` / the `/auth/google/callback` route)."""
    return f"{settings.PUBLIC_API_BASE_URL}/api/v1/auth/google/callback"


def encode_app_redirect(app_redirect_uri: str) -> str:
    """Pack the caller's real (non-https) redirect target into an encrypted
    `state` value — only this backend can produce or read it, so it can't be
    abused as an open redirect by a crafted `state` param."""
    return encrypt_token(app_redirect_uri)


def decode_app_redirect(state: str) -> str | None:
    try:
        return decrypt_token(state)
    except InvalidToken:
        return None


def build_authorize_url_with_relay(app_redirect_uri: str) -> str:
    """Authorize URL using the fixed relay redirect_uri, with the caller's
    real destination packed into `state`."""
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": relay_redirect_uri(),
        "response_type": "code",
        "scope": _SCOPES,
        "state": encode_app_redirect(app_redirect_uri),
        "prompt": "select_account",
    }
    return f"{_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code_for_id_token(code: str) -> str:
    """POST the OAuth `code` for an id_token — `redirect_uri` here must match
    the one used in the initial authorize request (the fixed relay URL, not
    the caller's own redirect_uri)."""
    data = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "code": code,
        "redirect_uri": relay_redirect_uri(),
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(_TOKEN_URL, data=data)
    if response.status_code >= 400:
        raise ExternalServiceError(f"Google token exchange failed ({response.status_code}): {response.text}")

    id_token = response.json().get("id_token")
    if not id_token:
        raise ExternalServiceError("Google token exchange did not return an id_token")
    return id_token
