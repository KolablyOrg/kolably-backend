"""
Unit tests for creator_service — repositories injected as fakes, no Supabase.
"""

import pytest
from fastapi import HTTPException

from app.schemas.creator import CreatorResponse
from app.services import creator_service

CREATOR_ROW = {
    "id": "c1",
    "profile_id": "p1",
    "name": "Alice",
    "username": "alice",
    "profile_photo_url": None,
    "niche": "food",
    "city": "Springfield",
    "follower_count": 1000,
    "engagement_rate": 3.5,
    "bio": "hello",
    "created_at": "2024-01-01T00:00:00+00:00",
    "tiktok_handle": None,
    "instagram_user_id": "ig-user",
    "instagram_access_token": "secret-token",
    "instagram_synced_at": None,
}


class FakeCreatorRepo:
    """Duck-typed stand-in for CreatorRepository."""

    def __init__(self, row=None, rows=(), total=0, creator_id="c1", active_count=0):
        self._row = row
        self._rows = list(rows)
        self._total = total
        self._creator_id = creator_id
        self._active_count = active_count

    async def get_by_id(self, creator_id: str):
        return self._row

    async def list_filtered(self, **kwargs):
        return self._rows, self._total

    async def get_id_by_profile_id(self, profile_id: str):
        return self._creator_id

    async def count_active_collaborations(self, creator_id: str):
        return self._active_count


async def test_get_creator_by_id_returns_none_when_missing():
    repo = FakeCreatorRepo(row=None)
    assert await creator_service.get_creator_by_id("missing", repo=repo) is None


async def test_get_creator_by_id_maps_user_id_from_profile_id():
    """Regression: user_id must come from profile_id (the FK IS the profile id),
    not from a joined profiles row that was never selected."""
    repo = FakeCreatorRepo(row=dict(CREATOR_ROW))

    creator = await creator_service.get_creator_by_id("c1", repo=repo)

    assert isinstance(creator, CreatorResponse)
    assert creator.user_id == "p1"
    assert creator.instagram_connected is True


async def test_get_creator_by_id_does_not_leak_instagram_tokens():
    repo = FakeCreatorRepo(row=dict(CREATOR_ROW))

    creator = await creator_service.get_creator_by_id("c1", repo=repo)
    dumped = creator.model_dump()

    assert "instagram_access_token" not in dumped
    assert "instagram_user_id" not in dumped


async def test_list_creators_uses_same_serialization_as_get():
    """One source of truth: list items are CreatorResponse objects identical
    to what the single-item path returns."""
    repo = FakeCreatorRepo(rows=[dict(CREATOR_ROW)], total=1)

    result = await creator_service.list_creators(repo=repo)

    assert result["total"] == 1
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert isinstance(item, CreatorResponse)
    assert item.model_dump() == creator_service._row_to_creator_response(dict(CREATOR_ROW)).model_dump()


async def test_get_creator_stats_404_without_creator_profile():
    repo = FakeCreatorRepo(creator_id=None)

    with pytest.raises(HTTPException) as exc_info:
        await creator_service.get_creator_stats(profile_id="p-missing", repo=repo)

    assert exc_info.value.status_code == 404


async def test_get_creator_stats_counts_active_collaborations():
    repo = FakeCreatorRepo(creator_id="c1", active_count=3)

    stats = await creator_service.get_creator_stats(profile_id="p1", repo=repo)

    assert stats["active_collaborations_count"] == 3
