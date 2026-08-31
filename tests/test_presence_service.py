from datetime import UTC

import pytest
from fastapi import HTTPException

from app.models.user import UserProfile
from app.services import presence_service


class FakeRedis:
    def __init__(self):
        self.calls = []

    async def set(self, *args, **kwargs):
        self.calls.append((args, kwargs))


class FakeProfileRepo:
    def __init__(self, profile=True):
        self.profile = profile
        self.calls = []

    async def update_last_seen_at(self, profile_id, last_seen_at):
        self.calls.append((profile_id, last_seen_at))
        if not self.profile:
            return None
        return UserProfile(
            id=profile_id,
            auth_id="auth",
            email="user@example.com",
            role="creator",
            last_seen_at=last_seen_at,
        )


@pytest.mark.asyncio
async def test_update_last_seen_writes_redis_and_repository_server_time(monkeypatch):
    redis = FakeRedis()
    repo = FakeProfileRepo()
    monkeypatch.setattr(presence_service, "get_redis_client", lambda: redis)

    result = await presence_service.update_last_seen("profile-1", repo=repo)

    assert result["last_seen_at"].tzinfo == UTC
    assert redis.calls == [(("presence:profile-1", "1"), {"ex": 90})]
    assert repo.calls[0][0] == "profile-1"
    assert repo.calls[0][1] == result["last_seen_at"]


@pytest.mark.asyncio
async def test_update_last_seen_continues_when_redis_fails(monkeypatch):
    class BrokenRedis:
        async def set(self, *args, **kwargs):
            raise RuntimeError("down")

    repo = FakeProfileRepo()
    monkeypatch.setattr(presence_service, "get_redis_client", lambda: BrokenRedis())
    result = await presence_service.update_last_seen("profile-1", repo=repo)
    assert result["last_seen_at"] == repo.calls[0][1]


@pytest.mark.asyncio
async def test_update_last_seen_returns_404_for_missing_profile(monkeypatch):
    monkeypatch.setattr(presence_service, "get_redis_client", lambda: None)
    with pytest.raises(HTTPException) as exc:
        await presence_service.update_last_seen("missing", repo=FakeProfileRepo(False))
    assert exc.value.status_code == 404
