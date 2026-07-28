"""
Shared test fixtures.
"""

import os

from cryptography.fernet import Fernet

# Tests exercise token encryption/decryption (Instagram connect/sync flows).
# Provide a throwaway per-run Fernet key so the suite doesn't depend on a
# local .env having TOKEN_ENCRYPTION_KEY set. A real env var always wins.
# Must happen before any `app.*` import, since `settings` is built at import time.
os.environ.setdefault("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)
