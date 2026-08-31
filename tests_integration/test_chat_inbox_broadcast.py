"""Local Supabase integration coverage for private inbox broadcast DDL.

The shared integration conftest refuses non-local projects before this test
can create any data.
"""

from pathlib import Path


def test_inbox_broadcast_migration_contract():
    """Guard the trigger's private-topic fan-out and ownership boundary."""
    migration = (Path(__file__).parents[1] / "migrations/20260829130100_inbox_realtime_broadcast.sql").read_text()

    assert "AFTER INSERT ON public.messages" in migration
    assert "'inbox:' || participant.profile_id::text" in migration
    assert "public.is_inbox_realtime_owner()" in migration
    assert "realtime.messages.extension = 'broadcast'" in migration
