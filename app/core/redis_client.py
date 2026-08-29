"""Shared Redis client used by presence and chat caches."""

from __future__ import annotations

import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: Redis | None = None


def get_redis_client() -> Redis | None:
    """Return the process-wide pooled client, or ``None`` when unconfigured."""
    global _client
    if _client is None and settings.REDIS_URL:
        _client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client


async def close_redis_client() -> None:
    """Close the shared pool during application shutdown."""
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except RedisError:
            logger.warning("Redis close failed", exc_info=True)
        finally:
            _client = None
