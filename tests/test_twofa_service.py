"""
Unit tests for twofa_service — custom TOTP 2FA. ProfileRepository is faked;
`app.core.crypto` runs for real against the throwaway TOKEN_ENCRYPTION_KEY
conftest.py sets, so encrypt/decrypt round-trips are exercised genuinely.
"""

import json
from datetime import UTC, datetime, timedelta

import pyotp
import pytest
from fastapi import HTTPException

from app.core.crypto import decrypt_token, encrypt_token
from app.models.user import UserProfile
from app.services import twofa_service

NOW = datetime(2026, 8, 14, 12, 0, 0, tzinfo=UTC)


def _profile(totp_secret_encrypted=None, totp_enabled=False, profile_id="profile-1", email="alice@example.com"):
    return UserProfile(
        id=profile_id,
        auth_id="auth-1",
        email=email,
        role="creator",
        created_at=NOW,
        totp_secret_encrypted=totp_secret_encrypted,
        totp_enabled=totp_enabled,
    )


class FakeProfileRepo:
    def __init__(self, profile):
        self._profile = profile
        self.update_calls: list[tuple[str, dict]] = []

    async def get_by_id(self, profile_id):
        return self._profile if self._profile and self._profile.id == profile_id else None

    async def update(self, profile_id, data):
        if not self._profile:
            return None
        for k, v in data.items():
            setattr(self._profile, k, v)
        self.update_calls.append((profile_id, data))
        return self._profile


async def test_setup_generates_secret_and_persists_encrypted():
    repo = FakeProfileRepo(_profile())
    result = await twofa_service.setup("profile-1", "alice@example.com", profile_repo=repo)

    assert "secret" in result and len(result["secret"]) > 0
    assert result["otpauth_url"].startswith("otpauth://totp/")
    persisted = repo.update_calls[0][1]["totp_secret_encrypted"]
    assert persisted != result["secret"]  # encrypted, not plaintext
    assert decrypt_token(persisted) == result["secret"]


async def test_enable_with_correct_code_succeeds():
    secret = pyotp.random_base32()
    repo = FakeProfileRepo(_profile(totp_secret_encrypted=encrypt_token(secret)))
    code = pyotp.TOTP(secret).now()

    result = await twofa_service.enable("profile-1", code, profile_repo=repo)

    assert result == {"enabled": True}
    assert repo.update_calls[-1] == ("profile-1", {"totp_enabled": True})


async def test_enable_with_wrong_code_fails():
    secret = pyotp.random_base32()
    repo = FakeProfileRepo(_profile(totp_secret_encrypted=encrypt_token(secret)))

    with pytest.raises(HTTPException) as exc_info:
        await twofa_service.enable("profile-1", "000000", profile_repo=repo)
    assert exc_info.value.status_code == 400


async def test_enable_without_setup_fails():
    repo = FakeProfileRepo(_profile())  # no secret at all
    with pytest.raises(HTTPException) as exc_info:
        await twofa_service.enable("profile-1", "123456", profile_repo=repo)
    assert exc_info.value.status_code == 400


async def test_disable_with_correct_code_succeeds():
    secret = pyotp.random_base32()
    repo = FakeProfileRepo(_profile(totp_secret_encrypted=encrypt_token(secret), totp_enabled=True))
    code = pyotp.TOTP(secret).now()

    result = await twofa_service.disable("profile-1", code, profile_repo=repo)

    assert result == {"enabled": False}
    assert repo.update_calls[-1] == (
        "profile-1", {"totp_enabled": False, "totp_secret_encrypted": None},
    )


async def test_disable_when_not_enabled_fails():
    repo = FakeProfileRepo(_profile())
    with pytest.raises(HTTPException) as exc_info:
        await twofa_service.disable("profile-1", "123456", profile_repo=repo)
    assert exc_info.value.status_code == 400


# ── login-time mfa_token roundtrip ───────────────────────────────────

def test_mint_mfa_token_embeds_real_tokens():
    token = twofa_service.mint_mfa_token(
        profile_id="profile-1", access_token="real-access", refresh_token="real-refresh"
    )
    payload = json.loads(decrypt_token(token))
    assert payload["access_token"] == "real-access"
    assert payload["refresh_token"] == "real-refresh"
    assert payload["profile_id"] == "profile-1"


async def test_verify_login_mfa_succeeds_with_correct_code():
    secret = pyotp.random_base32()
    repo = FakeProfileRepo(_profile(totp_secret_encrypted=encrypt_token(secret), totp_enabled=True))
    mfa_token = twofa_service.mint_mfa_token(
        profile_id="profile-1", access_token="real-access", refresh_token="real-refresh"
    )
    code = pyotp.TOTP(secret).now()

    result = await twofa_service.verify_login_mfa(mfa_token, code, profile_repo=repo)

    assert result["access_token"] == "real-access"
    assert result["refresh_token"] == "real-refresh"
    assert result["user"]["id"] == "profile-1"


async def test_verify_login_mfa_rejects_wrong_code():
    secret = pyotp.random_base32()
    repo = FakeProfileRepo(_profile(totp_secret_encrypted=encrypt_token(secret), totp_enabled=True))
    mfa_token = twofa_service.mint_mfa_token(
        profile_id="profile-1", access_token="real-access", refresh_token="real-refresh"
    )

    with pytest.raises(HTTPException) as exc_info:
        await twofa_service.verify_login_mfa(mfa_token, "000000", profile_repo=repo)
    assert exc_info.value.status_code == 400


async def test_verify_login_mfa_rejects_expired_token():
    secret = pyotp.random_base32()
    repo = FakeProfileRepo(_profile(totp_secret_encrypted=encrypt_token(secret), totp_enabled=True))
    expired_payload = {
        "profile_id": "profile-1",
        "access_token": "real-access",
        "refresh_token": "real-refresh",
        "exp": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
    }
    expired_token = encrypt_token(json.dumps(expired_payload))

    with pytest.raises(HTTPException) as exc_info:
        await twofa_service.verify_login_mfa(expired_token, pyotp.TOTP(secret).now(), profile_repo=repo)
    assert exc_info.value.status_code == 400


async def test_verify_login_mfa_rejects_garbage_token():
    with pytest.raises(HTTPException) as exc_info:
        await twofa_service.verify_login_mfa("not-a-real-token", "123456")
    assert exc_info.value.status_code == 400
