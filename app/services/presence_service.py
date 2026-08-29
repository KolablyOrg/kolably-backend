"""Presence heartbeat service."""

from datetime import UTC, datetime

from fastapi import HTTPException, status

from app.core.redis_client import get_redis_client
from app.repositories.profile_repo import ProfileRepository


async def update_last_seen(
    profile_id: str,
    *,
    repo: ProfileRepository | None = None,
) -> dict[str, datetime]:
    """Record a heartbeat in Redis and persist the authoritative server time."""
    now = datetime.now(UTC)
    client = get_redis_client()
    if client is not None:
        try:
            await client.set(f"presence:{profile_id}", "1", ex=90)
        except Exception:
            # Redis is an acceleration layer; a database write still makes the
            # heartbeat useful for recently-active status.
            import logging

            logging.getLogger(__name__).warning("Redis presence write failed", exc_info=True)

    profile = await (repo or ProfileRepository()).update_last_seen_at(profile_id, now)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User profile not found")
    return {"last_seen_at": profile.last_seen_at or now}
