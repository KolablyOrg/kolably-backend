"""
Unit tests for:
- `creator_service.refresh_all_instagram_stats` — the daily batch job that
  refreshes every connected creator's live Instagram stats and snapshots
  them into `creator_stats_history` (see app/core/scheduler.py for what
  actually calls this on a schedule).
- `instagram_service.calculate_engagement_rate`'s per-media-item resilience
  fix — one post's insights call failing shouldn't null out an otherwise
  healthy account's engagement rate.

Instagram Graph API calls are faked, no real network/DB calls.
"""

from datetime import UTC, datetime, timedelta

import httpx

from app.core.crypto import encrypt_token
from app.core.exceptions import ExternalServiceError
from app.models.creator import Creator
from app.services import creator_service, instagram_service


def _make_connected_creator(creator_id: str, profile_id: str) -> Creator:
    return Creator(
        id=creator_id,
        profile_id=profile_id,
        name="Creator",
        instagram_user_id=f"ig-{creator_id}",
        instagram_access_token=encrypt_token("valid-tok"),
        # Relative to actual wall-clock time, not a fixed fixture date — the
        # code under test compares against datetime.now(UTC) directly, and a
        # fixed past timestamp here would eventually drift into the refresh
        # threshold as real time passes (see test_instagram_connect.py for
        # the same fix after this exact pattern broke CI).
        instagram_token_expires_at=(datetime.now(UTC) + timedelta(days=30)).isoformat(),
        instagram_synced_at=None,
    )


class FakeBatchCreatorRepo:
    """Minimal fake covering only what `refresh_all_instagram_stats` touches."""

    def __init__(self, creators: list[Creator]):
        self._creators = creators
        self.updated_profile_ids: list[str] = []
        self.snapshot_called = False

    async def list_instagram_connected(self):
        return list(self._creators)

    async def update_by_profile_id(self, profile_id, data):
        self.updated_profile_ids.append(profile_id)
        creator = next(c for c in self._creators if c.profile_id == profile_id)
        for key, value in data.items():
            setattr(creator, key, value)
        return creator

    async def snapshot_all_creators(self):
        self.snapshot_called = True


def _patch_instagram_service(monkeypatch):
    async def fake_refresh_long_lived_token(token):
        return {"access_token": "refreshed-tok", "expires_in": 5183854}

    async def fake_fetch_profile(access_token):
        return {"followers_count": 500, "follows_count": 10, "profile_picture_url": "https://cdn/pfp.jpg"}

    async def fake_fetch_media(access_token):
        return [{"id": "m1", "media_type": "IMAGE"}]

    async def fake_calculate_engagement_and_views(access_token, media):
        return 7.25, 1234, {}

    monkeypatch.setattr(creator_service.instagram_service, "refresh_long_lived_token", fake_refresh_long_lived_token)
    monkeypatch.setattr(creator_service.instagram_service, "fetch_profile", fake_fetch_profile)
    monkeypatch.setattr(creator_service.instagram_service, "fetch_media", fake_fetch_media)
    monkeypatch.setattr(
        creator_service.instagram_service, "calculate_engagement_and_views", fake_calculate_engagement_and_views
    )


async def test_refresh_all_instagram_stats_updates_every_connected_creator(monkeypatch):
    _patch_instagram_service(monkeypatch)
    creators = [_make_connected_creator("c1", "p1"), _make_connected_creator("c2", "p2")]
    repo = FakeBatchCreatorRepo(creators)

    result = await creator_service.refresh_all_instagram_stats(repo=repo)

    assert result == {"total": 2, "refreshed": 2, "failed": 0}
    assert sorted(repo.updated_profile_ids) == ["p1", "p2"]
    assert repo.snapshot_called is True
    assert creators[0].engagement_rate == 7.25
    assert creators[0].follower_count == 500
    assert creators[0].views_count == 1234


async def test_refresh_all_instagram_stats_isolates_per_creator_failures(monkeypatch):
    """Regression: one creator with a revoked/expired token, or any other
    per-creator Instagram API failure, must not stop the rest of the batch
    from refreshing — and the snapshot must still run for whoever succeeded."""
    _patch_instagram_service(monkeypatch)
    creators = [_make_connected_creator("c1", "p1"), _make_connected_creator("c2", "p2")]
    repo = FakeBatchCreatorRepo(creators)

    calls = {"n": 0}
    working_fetch_profile = creator_service.instagram_service.fetch_profile

    async def fails_on_first_call(access_token):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ExternalServiceError("Instagram API error (401): token revoked")
        return await working_fetch_profile(access_token)

    monkeypatch.setattr(creator_service.instagram_service, "fetch_profile", fails_on_first_call)

    result = await creator_service.refresh_all_instagram_stats(repo=repo)

    assert result == {"total": 2, "refreshed": 1, "failed": 1}
    assert repo.updated_profile_ids == ["p2"]  # p1 failed before its update call
    assert repo.snapshot_called is True  # still runs even though one creator failed


async def test_refresh_all_instagram_stats_noop_when_nobody_connected(monkeypatch):
    _patch_instagram_service(monkeypatch)
    repo = FakeBatchCreatorRepo([])

    result = await creator_service.refresh_all_instagram_stats(repo=repo)

    assert result == {"total": 0, "refreshed": 0, "failed": 0}
    assert repo.snapshot_called is True  # snapshot still runs (no-ops on 0 rows)


async def test_calculate_engagement_rate_skips_media_item_with_failed_insights(monkeypatch):
    """Regression: previously a single media item's insights call raising
    (deprecated metric, expired story, transient Graph API error, ...)
    would blow up the whole calculation instead of just being excluded."""
    calls = []

    async def fake_fetch_media_insights(access_token, media_id, media_type):
        calls.append(media_id)
        if media_id == "bad-post":
            raise ExternalServiceError("Instagram API error (400): metric not available for this media type")
        return {"reach": 100, "likes": 10, "comments": 5}

    monkeypatch.setattr(instagram_service, "fetch_media_insights", fake_fetch_media_insights)

    media = [{"id": "bad-post", "media_type": "IMAGE"}, {"id": "good-post", "media_type": "IMAGE"}]
    result = await instagram_service.calculate_engagement_rate("tok", media)

    assert calls == ["bad-post", "good-post"]
    assert result == 15.0  # (10 + 5) / 100 * 100 — from the one good post only


async def test_calculate_engagement_rate_returns_none_when_every_item_fails(monkeypatch):
    async def always_failing(access_token, media_id, media_type):
        raise ExternalServiceError("Instagram API error (400): boom")

    monkeypatch.setattr(instagram_service, "fetch_media_insights", always_failing)

    result = await instagram_service.calculate_engagement_rate("tok", [{"id": "m1", "media_type": "IMAGE"}])

    assert result is None


async def test_calculate_engagement_rate_returns_none_for_no_media():
    assert await instagram_service.calculate_engagement_rate("tok", []) is None


async def test_calculate_engagement_and_views_returns_views_by_permalink_for_video_items(monkeypatch):
    """The per-permalink view map is what `_refresh_instagram_stats` uses to
    backfill stale `portfolio_items.view_count` rows (see
    `creator_service._backfill_portfolio_view_counts`) — it must only
    include video items (Instagram never reports views for photos) and use
    the same view counts already fetched for the aggregate `total_views`
    stat, at no extra API cost."""

    async def fake_fetch_media_insights(access_token, media_id, media_type):
        insights = {"reach": 100, "likes": 10, "comments": 5}
        if media_type != "IMAGE":
            insights["views"] = 42
        return insights

    monkeypatch.setattr(instagram_service, "fetch_media_insights", fake_fetch_media_insights)

    media = [
        {"id": "video-1", "media_type": "VIDEO", "permalink": "https://instagram.com/p/video-1/"},
        {"id": "photo-1", "media_type": "IMAGE", "permalink": "https://instagram.com/p/photo-1/"},
    ]
    engagement_rate, total_views, views_by_permalink = await instagram_service.calculate_engagement_and_views(
        "tok", media
    )

    assert total_views == 42  # only the video item reports views
    assert views_by_permalink == {"https://instagram.com/p/video-1/": 42}


async def test_calculate_engagement_and_views_skips_item_on_transport_level_failure(monkeypatch):
    """Regression: a transport-level failure (blocked proxy, dropped
    connection, timeout, ...) from `fetch_media_insights` previously wasn't
    caught here — only `ExternalServiceError` (HTTP-status errors) was —
    so it crashed the whole call instead of just being excluded like any
    other single bad item."""
    calls = []

    async def fake_fetch_media_insights(access_token, media_id, media_type):
        calls.append(media_id)
        if media_id == "unreachable":
            raise httpx.ConnectError("connection refused")
        return {"reach": 100, "likes": 10, "comments": 5}

    monkeypatch.setattr(instagram_service, "fetch_media_insights", fake_fetch_media_insights)

    media = [
        {"id": "unreachable", "media_type": "IMAGE", "permalink": "https://instagram.com/p/unreachable/"},
        {"id": "good-post", "media_type": "IMAGE", "permalink": "https://instagram.com/p/good-post/"},
    ]
    result = await instagram_service.calculate_engagement_rate("tok", media)

    assert calls == ["unreachable", "good-post"]
    assert result == 15.0  # (10 + 5) / 100 * 100 — from the one good post only
