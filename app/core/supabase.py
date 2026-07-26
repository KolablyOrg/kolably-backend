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

from supabase import AsyncClient, create_async_client

from app.core.config import settings


async def get_supabase_client() -> AsyncClient:
    """Get Supabase client with anon key (for auth operations)."""
    return await create_async_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


async def get_supabase_admin_client() -> AsyncClient:
    """Get Supabase client with service-role key (bypasses RLS — see module docstring)."""
    return await create_async_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
