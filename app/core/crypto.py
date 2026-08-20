"""
Symmetric encryption for secrets stored at rest (e.g. `creators.instagram_access_token`).

Uses Fernet (AES-128-CBC + HMAC) keyed by `TOKEN_ENCRYPTION_KEY`.
"""

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    if not settings.TOKEN_ENCRYPTION_KEY:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is not set")
    return Fernet(settings.TOKEN_ENCRYPTION_KEY.encode())


def encrypt_token(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()


def decrypt_token_if_encrypted(value: str | None) -> str | None:
    """Like `decrypt_token`, but tolerates a value written before a field
    started being encrypted (e.g. PAN numbers stored in plaintext by older
    code). Falls back to the raw value instead of raising, so a rollout of
    encryption-at-rest doesn't break reads of pre-existing rows — new writes
    always go through `encrypt_token`, so this fallback naturally stops
    being hit once every row has been re-saved at least once."""
    if not value:
        return value
    try:
        return decrypt_token(value)
    except (InvalidToken, ValueError):
        return value
