"""
Supabase client initialisation.

Two async clients (`supabase.AsyncClient`, so every `.execute()`/auth call is
genuinely awaitable and never blocks the event loop):
- `get_supabase_client()` (anon key) — auth operations only (signup, login, etc.). Respects RLS.
- `get_supabase_admin_client()` (service-role key) — all other DB reads/writes.

⚠️  The admin client BYPASSES Row Level Security on every query. That is
intentional: authorization (ownership/role checks) is enforced in Python in
the service layer (`_ensure_campaign_owner`-style helpers), with no DB-level
backstop. Never let user-supplied IDs reach a query unverified.

Note: clients are created fresh per call, not cached as singletons — httpx
clients bind to the event loop that created them, and a shared client breaks
under pytest/TestClient (and is unsafe across loops in general).
"""

from app.core.config import settings
from supabase import AsyncClient, AsyncClientOptions, create_async_client


def _static_key_options(key: str) -> AsyncClientOptions:
    """Pre-set the Authorization header so `AsyncClient.create()` skips its
    `auth.get_session()` call. That call only matters for a real end-user
    session (browser-style auth); both our clients use a static API key
    (anon/service-role), so the lookup is pure dead weight — and, worse, an
    extra network round-trip to Supabase Auth on every single repository
    instantiation, since clients are deliberately created fresh per call
    (see module docstring)."""
    return AsyncClientOptions(headers={"Authorization": f"Bearer {key}"})


async def get_supabase_client() -> AsyncClient:
    """Get Supabase client with anon key (for auth operations)."""
    return await create_async_client(
        settings.SUPABASE_URL, settings.SUPABASE_KEY, options=_static_key_options(settings.SUPABASE_KEY)
    )


async def get_supabase_admin_client() -> AsyncClient:
    """Get Supabase client with service-role key (bypasses RLS — see module docstring)."""
    return await create_async_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY,
        options=_static_key_options(settings.SUPABASE_SERVICE_ROLE_KEY),
    )
