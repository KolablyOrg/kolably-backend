"""
Symmetric encryption for secrets stored at rest (e.g. `creators.instagram_access_token`).

Uses Fernet (AES-128-CBC + HMAC) keyed by `TOKEN_ENCRYPTION_KEY`.
"""

from functools import lru_cache

from cryptography.fernet import Fernet

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
