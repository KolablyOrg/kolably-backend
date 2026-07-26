"""
Supabase client initialisation.

Two clients:
- `supabase` (anon key) — for auth operations (signup, login, etc.)
- `supabase_admin` (service role key) — for DB operations bypassing RLS
"""

from supabase import Client, create_client

from app.core.config import settings


def get_supabase_client() -> Client:
    """Get Supabase client with anon key (for auth operations)."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


def get_supabase_admin_client() -> Client:
    """Get Supabase client with service role key (bypasses RLS)."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
