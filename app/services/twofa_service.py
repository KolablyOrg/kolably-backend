"""
Custom TOTP two-factor authentication.

Not Supabase's built-in MFA (see the plan note in app/services/business_access.py-
adjacent docs) — this backend never inspects the `aal` JWT claim, so a
Supabase-MFA'd login would still hand out a fully-valid token before the
second factor was ever checked. Gating token issuance in `auth_service.login`
itself (via a short-lived `mfa_token`, below) closes that gap without
changing how tokens are verified anywhere else in the app.

`mfa_token` reuses `app.core.crypto`'s Fernet cipher (same key that already
encrypts `creators.instagram_access_token`) rather than adding a second
signing secret — it's just JSON ciphertext embedding the real tokens plus an
expiry, decrypted and time-checked in `verify_login_mfa`.
"""

import json
from datetime import UTC, datetime, timedelta

import pyotp
from fastapi import HTTPException, status

from app.core.crypto import decrypt_token, encrypt_token
from app.repositories.profile_repo import ProfileRepository

MFA_TOKEN_TTL_SECONDS = 300


def generate_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name="Kolably")


def verify_code(secret: str, code: str) -> bool:
    return pyotp.totp.TOTP(secret).verify(code, valid_window=1)


async def setup(profile_id: str, email: str, *, profile_repo: ProfileRepository | None = None) -> dict:
    """Generate a new secret and stash it (not yet enabled) so `enable` can
    verify against it without re-generating — one secret per setup attempt."""
    profile_repo = profile_repo or ProfileRepository()
    secret = generate_secret()
    updated = await profile_repo.update(profile_id, {"totp_secret_encrypted": encrypt_token(secret)})
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return {"secret": secret, "otpauth_url": provisioning_uri(secret, email)}


async def enable(profile_id: str, code: str, *, profile_repo: ProfileRepository | None = None) -> dict:
    profile_repo = profile_repo or ProfileRepository()
    profile = await profile_repo.get_by_id(profile_id)
    if not profile or not profile.totp_secret_encrypted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Call setup first to generate a code",
        )
    secret = decrypt_token(profile.totp_secret_encrypted)
    if not verify_code(secret, code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect code")

    await profile_repo.update(profile_id, {"totp_enabled": True})
    return {"enabled": True}


async def disable(profile_id: str, code: str, *, profile_repo: ProfileRepository | None = None) -> dict:
    profile_repo = profile_repo or ProfileRepository()
    profile = await profile_repo.get_by_id(profile_id)
    if not profile or not profile.totp_enabled or not profile.totp_secret_encrypted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA is not enabled")
    secret = decrypt_token(profile.totp_secret_encrypted)
    if not verify_code(secret, code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect code")

    await profile_repo.update(profile_id, {"totp_enabled": False, "totp_secret_encrypted": None})
    return {"enabled": False}


def mint_mfa_token(*, profile_id: str, access_token: str, refresh_token: str) -> str:
    """Package real Supabase tokens behind a 2FA gate — see module docstring."""
    payload = {
        "profile_id": profile_id,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "exp": (datetime.now(UTC) + timedelta(seconds=MFA_TOKEN_TTL_SECONDS)).isoformat(),
    }
    return encrypt_token(json.dumps(payload))


async def verify_login_mfa(
    mfa_token: str,
    code: str,
    *,
    profile_repo: ProfileRepository | None = None,
) -> dict:
    """Decode `mfa_token`, verify the TOTP code, and release the embedded
    tokens — the second half of a 2FA-gated login."""
    try:
        payload = json.loads(decrypt_token(mfa_token))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired login session"
        ) from exc

    if datetime.now(UTC) > datetime.fromisoformat(payload["exp"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This login attempt expired — sign in again",
        )

    profile_repo = profile_repo or ProfileRepository()
    profile = await profile_repo.get_by_id(payload["profile_id"])
    if not profile or not profile.totp_enabled or not profile.totp_secret_encrypted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA is not enabled")

    secret = decrypt_token(profile.totp_secret_encrypted)
    if not verify_code(secret, code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect code")

    return {
        "access_token": payload["access_token"],
        "refresh_token": payload["refresh_token"],
        "token_type": "bearer",
        "user": {
            "id": profile.id,
            "email": profile.email,
            "role": profile.role.value if hasattr(profile.role, "value") else profile.role,
            "is_active": profile.is_active,
        },
    }
