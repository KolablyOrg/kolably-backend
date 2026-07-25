"""
Security utilities — Supabase JWT verification.

Supports both legacy HS256 (symmetric JWT secret) and modern
ES256/RS256 (asymmetric signing keys, verified via the project's JWKS endpoint).
"""

import time

import httpx
from fastapi import HTTPException, status
from jose import JWTError, jwt

from app.core.config import settings

# Simple in-memory JWKS cache: {"keys": [...], "fetched_at": float}
_jwks_cache: dict = {"keys": [], "fetched_at": 0.0}
_JWKS_TTL_SECONDS = 600  # 10 minutes


def _get_jwks() -> list[dict]:
    """Fetch the project's JWKS (public signing keys), with caching."""
    now = time.time()
    if _jwks_cache["keys"] and (now - _jwks_cache["fetched_at"]) < _JWKS_TTL_SECONDS:
        return _jwks_cache["keys"]

    url = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
    response = httpx.get(url, timeout=10.0)
    response.raise_for_status()
    keys = response.json().get("keys", [])

    _jwks_cache["keys"] = keys
    _jwks_cache["fetched_at"] = now
    return keys


def verify_supabase_token(token: str) -> dict:
    """
    Decode and verify a Supabase-issued JWT.

    Returns the decoded payload dict on success.
    Raises HTTPException on failure.
    """
    try:
        headers = jwt.get_unverified_headers(token)
        alg = headers.get("alg", "HS256")

        if alg == "HS256":
            # Legacy symmetric verification with the JWT secret
            payload = jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
            )
        else:
            # Asymmetric verification (ES256/RS256) via JWKS public key
            kid = headers.get("kid")
            keys = _get_jwks()
            jwk = next((k for k in keys if k.get("kid") == kid), None)
            if jwk is None:
                # Key may have rotated — refresh cache once and retry
                _jwks_cache["fetched_at"] = 0.0
                keys = _get_jwks()
                jwk = next((k for k in keys if k.get("kid") == kid), None)
            if jwk is None:
                raise JWTError("No matching signing key found in JWKS")

            payload = jwt.decode(
                token,
                jwk,
                algorithms=[alg],
                audience="authenticated",
            )
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )
