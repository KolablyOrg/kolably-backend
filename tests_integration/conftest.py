"""
Shared fixtures for the integration suite.

Unlike tests/ (services exercised against fake/mocked repositories), these
tests hit a REAL Postgres + Supabase Auth instance over the network — the
layer the unit suite deliberately skips. They're meant to run against a
`supabase start` local instance only. See tests_integration/README.md for
how to run them; CI wires this up in .github/workflows/deploy.yml.
"""

import os
import uuid

from cryptography.fernet import Fernet

# Must happen before any `app.*` import — Settings() is built at import time,
# same reason tests/conftest.py does this.
os.environ.setdefault("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _guard_against_non_local_supabase():
    """Refuse to run unless SUPABASE_URL clearly points at a local instance.

    These tests create real auth users and rows through the real API. If
    SUPABASE_URL/KEY/SERVICE_ROLE_KEY aren't overridden from `supabase
    start`'s output before pytest runs, Settings() falls back to whatever
    .env has — which, on a developer machine, is often the real project.
    Running this suite there would create junk users and rows against it.
    """
    url = settings.SUPABASE_URL
    if not any(marker in url for marker in ("127.0.0.1", "localhost")):
        pytest.exit(
            f"Refusing to run tests_integration/ against non-local SUPABASE_URL={url!r}. "
            "Run `supabase start` from kolably_backend/ and export its env vars first "
            "(see tests_integration/README.md).",
            returncode=1,
        )


@pytest.fixture
def client():
    """FastAPI test client, talking to the real local Supabase instance."""
    return TestClient(app)


def unique_email(prefix: str) -> str:
    """A fresh, collision-free email per call — tests don't share signups
    and don't rely on any DB reset between runs.

    Uses a real, deliverable-looking domain rather than something under a
    reserved TLD like .test/.example/.invalid — email-validator (used by
    Pydantic's EmailStr) rejects those outright as "special-use" domains,
    independent of anything Supabase itself would check. Nothing here ever
    sends real mail: the local Supabase instance's Auth email delivery is
    captured by its bundled Mailpit/Inbucket, never actually sent out.
    """
    return f"integration-test+{prefix}-{uuid.uuid4().hex[:12]}@kolably.com"
