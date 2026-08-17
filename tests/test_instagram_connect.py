"""
Unit tests for the Instagram connect/sync/disconnect/import-portfolio flow —
used by creators who signed up via Google/email and connect Instagram during
onboarding (as opposed to `/auth/instagram`, which signs up *with* Instagram
directly). Instagram Graph API calls are faked, no real network/DB calls.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.core.crypto import decrypt_token, encrypt_token
from app.models.creator import Creator, PortfolioItem
from app.services import creator_service, instagram_service

CREATOR_ROW = {
    "id": "creator-1",
    "profile_id": "profile-1",
    "name": "Alice",
    "username": "alice",
    "profile_photo_url": None,
    "niche": "food",
    "city": "Springfield",
    "follower_count": 100,
    "engagement_rate": None,
    "bio": "self-reported bio",
    "created_at": "2024-01-01T00:00:00+00:00",
    "tiktok_handle": None,
    "instagram_user_id": None,
    "instagram_access_token": None,
    "instagram_token_expires_at": None,
    "instagram_synced_at": None,
}

IG_PROFILE = {
    "user_id": 17841441112302348,
    "username": "kolablyofficial",
    "name": "Kolably",
    "biography": "Connect with nearby creators",
    "website": "https://www.kolably.com/",
    "account_type": "BUSINESS",
    "followers_count": 304,
    "follows_count": 5,
    "media_count": 3,
    "profile_picture_url": "https://cdn.instagram.com/pfp.jpg",
}

IG_MEDIA = [
    {
        "id": "18072607637226798",
        "media_type": "VIDEO",
        "media_url": "https://cdn.instagram.com/reel.mp4",
        "permalink": "https://www.instagram.com/reel/DWOy5imk5Ln/",
        "like_count": 1,
        "comments_count": 0,
    },
]


def _make_creator(data: dict) -> Creator:
    return Creator(
        id=data.get("id", "creator-x"),
        profile_id=data["profile_id"],
        name=data.get("name", ""),
        username=data.get("username"),
        city=data.get("city"),
        niche=data.get("niche"),
        follower_count=data.get("follower_count"),
        bio=data.get("bio"),
        instagram_handle=data.get("instagram_handle"),
        engagement_rate=data.get("engagement_rate"),
        profile_photo_url=data.get("profile_photo_url"),
        created_at=data.get("created_at", "2024-01-01T00:00:00+00:00"),
        tiktok_handle=data.get("tiktok_handle"),
        instagram_user_id=data.get("instagram_user_id"),
        instagram_access_token=data.get("instagram_access_token"),
        instagram_token_expires_at=data.get("instagram_token_expires_at"),
        instagram_synced_at=data.get("instagram_synced_at"),
        instagram_connected=bool(data.get("instagram_user_id")),
        website=data.get("website"),
        following_count=data.get("following_count"),
    )


def _make_portfolio_item(data: dict) -> PortfolioItem:
    return PortfolioItem.from_row(data)


class FakeCreatorRepo:
    def __init__(self, creator=None, other_by_ig_id=None, existing_portfolio=()):
        self._creator = creator
        self._other_by_ig_id = other_by_ig_id
        self._existing_portfolio = list(existing_portfolio)
        self.updated = None
        self.updated_profile_id = None
        self.portfolio_inserted = None
        self.portfolio_updated = []

    async def get_by_profile_id(self, profile_id):
        return _make_creator(self._creator) if self._creator else None

    async def get_by_instagram_user_id(self, instagram_user_id):
        return _make_creator(self._other_by_ig_id) if self._other_by_ig_id else None

    async def update_by_profile_id(self, profile_id, data):
        self.updated_profile_id = profile_id
        self.updated = data
        return _make_creator({**self._creator, **data})

    async def insert_portfolio_items(self, items):
        self.portfolio_inserted = items
        return [
            _make_portfolio_item({**item, "id": f"pi-{i}", "created_at": "2026-01-01T00:00:00+00:00"})
            for i, item in enumerate(items)
        ]

    async def get_portfolio_items_by_post_links(self, creator_id, post_links):
        return [
            _make_portfolio_item(row)
            for row in self._existing_portfolio
            if row.get("post_link") in post_links
        ]

    async def update_portfolio_item(self, item_id, data):
        self.portfolio_updated.append((item_id, data))
        existing = next((r for r in self._existing_portfolio if r["id"] == item_id), None)
        return _make_portfolio_item({**existing, **data}) if existing else None

    async def sum_portfolio_views(self, creator_id):
        return sum(int(row.get("view_count") or 0) for row in self._existing_portfolio)


def _patch_instagram_service(monkeypatch, refresh_calls=None):
    async def fake_exchange_code_for_token(code, redirect_uri):
        return {"access_token": "short-lived-tok", "user_id": "999"}

    async def fake_exchange_for_long_lived_token(short_lived_token):
        return {"access_token": "long-lived-tok", "expires_in": 5183854}

    async def fake_refresh_long_lived_token(token):
        if refresh_calls is not None:
            refresh_calls.append(token)
        return {"access_token": "refreshed-tok", "expires_in": 5183854}

    async def fake_fetch_profile(access_token):
        return IG_PROFILE

    async def fake_fetch_media(access_token):
        return IG_MEDIA

    async def fake_calculate_engagement_rate(access_token, media):
        return 12.5

    monkeypatch.setattr(creator_service.instagram_service, "exchange_code_for_token", fake_exchange_code_for_token)
    monkeypatch.setattr(
        creator_service.instagram_service, "exchange_for_long_lived_token", fake_exchange_for_long_lived_token
    )
    monkeypatch.setattr(creator_service.instagram_service, "refresh_long_lived_token", fake_refresh_long_lived_token)
    monkeypatch.setattr(creator_service.instagram_service, "fetch_profile", fake_fetch_profile)
    monkeypatch.setattr(creator_service.instagram_service, "fetch_media", fake_fetch_media)
    monkeypatch.setattr(creator_service.instagram_service, "calculate_engagement_rate", fake_calculate_engagement_rate)


async def test_get_instagram_auth_url_includes_redirect_and_scope():
    result = await creator_service.get_instagram_auth_url("http://localhost:8080/")

    assert "instagram.com/oauth/authorize" in result["url"]
    assert "redirect_uri=" in result["url"]
    assert "instagram_business_manage_insights" in result["url"]


async def test_get_instagram_auth_url_uses_fixed_relay_not_client_uri():
    """Regression: Instagram rejects any redirect_uri that isn't https —
    a client's own exp://.../mobile://... scheme can never be registered
    with Meta, so the authorize URL must always point at this backend's
    fixed relay endpoint instead, with the client's real destination
    packed into `state`."""
    from urllib.parse import parse_qs, urlparse

    app_redirect = "exp://192.168.1.8:3000/--/auth/instagram/callback"
    result = await creator_service.get_instagram_auth_url(app_redirect)

    query = parse_qs(urlparse(result["url"]).query)
    assert query["redirect_uri"][0] == instagram_service.relay_redirect_uri()
    assert app_redirect not in result["url"]
    assert instagram_service.decode_app_redirect(query["state"][0]) == app_redirect


def test_decode_app_redirect_rejects_tampered_state():
    real_state = instagram_service.encode_app_redirect("mobile://auth/instagram/callback")
    assert instagram_service.decode_app_redirect(real_state[:-1] + "x") is None


async def test_connect_instagram_prefills_profile(monkeypatch):
    _patch_instagram_service(monkeypatch)
    repo = FakeCreatorRepo(creator=dict(CREATOR_ROW))

    result = await creator_service.connect_instagram(
        profile_id="profile-1", code="auth-code", redirect_uri="http://localhost:8080/", repo=repo
    )

    assert result.follower_count == 304
    assert result.following_count == 5
    assert result.bio == "Connect with nearby creators"
    assert result.instagram_connected is True
    assert repo.updated["instagram_user_id"] == "17841441112302348"
    assert decrypt_token(repo.updated["instagram_access_token"]) == "long-lived-tok"


async def test_connect_instagram_rejects_personal_account(monkeypatch):
    _patch_instagram_service(monkeypatch)

    async def fake_fetch_profile(access_token):
        return {**IG_PROFILE, "account_type": "PERSONAL"}

    monkeypatch.setattr(creator_service.instagram_service, "fetch_profile", fake_fetch_profile)
    repo = FakeCreatorRepo(creator=dict(CREATOR_ROW))

    with pytest.raises(HTTPException) as exc_info:
        await creator_service.connect_instagram(
            profile_id="profile-1", code="auth-code", redirect_uri="http://localhost:8080/", repo=repo
        )

    assert exc_info.value.status_code == 422
    assert repo.updated is None


async def test_connect_instagram_rejects_already_connected_elsewhere(monkeypatch):
    _patch_instagram_service(monkeypatch)
    repo = FakeCreatorRepo(
        creator=dict(CREATOR_ROW),
        other_by_ig_id={"profile_id": "someone-else"},
    )

    with pytest.raises(HTTPException) as exc_info:
        await creator_service.connect_instagram(
            profile_id="profile-1", code="auth-code", redirect_uri="http://localhost:8080/", repo=repo
        )

    assert exc_info.value.status_code == 409
    assert repo.updated is None


async def test_connect_instagram_404_without_creator_profile(monkeypatch):
    _patch_instagram_service(monkeypatch)
    repo = FakeCreatorRepo(creator=None)

    with pytest.raises(HTTPException) as exc_info:
        await creator_service.connect_instagram(
            profile_id="profile-missing", code="auth-code", redirect_uri="http://localhost:8080/", repo=repo
        )

    assert exc_info.value.status_code == 404


async def test_sync_instagram_refreshes_stats_only_when_token_still_fresh(monkeypatch):
    refresh_calls = []
    _patch_instagram_service(monkeypatch, refresh_calls=refresh_calls)

    connected = {
        **CREATOR_ROW,
        "instagram_user_id": "17841441112302348",
        "instagram_access_token": encrypt_token("still-valid-tok"),
        # Relative to actual wall-clock time — the code under test compares
        # against datetime.now(UTC) directly, not a fixture, so a fixed past
        # timestamp here would silently drift into the refresh threshold as
        # real time passes (this is exactly what broke this test).
        "instagram_token_expires_at": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
    }
    repo = FakeCreatorRepo(creator=connected)

    result = await creator_service.sync_instagram(profile_id="profile-1", repo=repo)

    assert refresh_calls == []  # not near expiry — no refresh call made
    assert result.follower_count == 304
    assert result.following_count == 5
    assert "name" not in repo.updated
    assert "bio" not in repo.updated


async def test_sync_instagram_proactively_refreshes_near_expiry_token(monkeypatch):
    refresh_calls = []
    _patch_instagram_service(monkeypatch, refresh_calls=refresh_calls)

    connected = {
        **CREATOR_ROW,
        "instagram_user_id": "17841441112302348",
        "instagram_access_token": encrypt_token("almost-expired-tok"),
        "instagram_token_expires_at": (datetime.now(UTC) + timedelta(days=3)).isoformat(),
    }
    repo = FakeCreatorRepo(creator=connected)

    await creator_service.sync_instagram(profile_id="profile-1", repo=repo)

    assert refresh_calls == ["almost-expired-tok"]
    assert decrypt_token(repo.updated["instagram_access_token"]) == "refreshed-tok"


async def test_sync_instagram_not_connected_422(monkeypatch):
    _patch_instagram_service(monkeypatch)
    repo = FakeCreatorRepo(creator=dict(CREATOR_ROW))  # instagram_access_token is None

    with pytest.raises(HTTPException) as exc_info:
        await creator_service.sync_instagram(profile_id="profile-1", repo=repo)

    assert exc_info.value.status_code == 422


async def test_disconnect_instagram_clears_stored_fields(monkeypatch):
    connected = {
        **CREATOR_ROW,
        "instagram_user_id": "17841441112302348",
        "instagram_access_token": encrypt_token("some-tok"),
    }
    repo = FakeCreatorRepo(creator=connected)

    await creator_service.disconnect_instagram(profile_id="profile-1", repo=repo)

    assert repo.updated == {
        "instagram_user_id": None,
        "instagram_access_token": None,
        "instagram_token_expires_at": None,
        "instagram_synced_at": None,
    }


async def test_disconnect_instagram_404_without_creator_profile():
    repo = FakeCreatorRepo(creator=None)

    with pytest.raises(HTTPException) as exc_info:
        await creator_service.disconnect_instagram(profile_id="profile-missing", repo=repo)

    assert exc_info.value.status_code == 404


async def test_import_instagram_portfolio_inserts_items(monkeypatch):
    _patch_instagram_service(monkeypatch)
    connected = {
        **CREATOR_ROW,
        "instagram_access_token": encrypt_token("some-tok"),
    }
    repo = FakeCreatorRepo(creator=connected)

    items = await creator_service.import_instagram_portfolio(profile_id="profile-1", repo=repo)

    assert len(items) == 1
    assert items[0]["media_url"] == IG_MEDIA[0]["media_url"]
    assert items[0]["media_type"] == "video"
    assert repo.portfolio_inserted[0]["creator_id"] == "creator-1"


async def test_import_instagram_portfolio_refreshes_existing_item_instead_of_duplicating(monkeypatch):
    """Regression: a reel imported before the thumbnail-extraction fix landed
    could be stuck with a stale, broken media_url (the raw video file, not a
    displayable thumbnail) forever, since import previously only ever
    inserted. Re-selecting the same post (matched by its stable permalink)
    must update the existing row in place with the now-correct thumbnail,
    not create a duplicate."""
    _patch_instagram_service(monkeypatch)

    async def fake_fetch_media(access_token):
        return [{**IG_MEDIA[0], "thumbnail_url": "https://cdn.instagram.com/reel-thumb.jpg"}]

    monkeypatch.setattr(creator_service.instagram_service, "fetch_media", fake_fetch_media)

    connected = {**CREATOR_ROW, "instagram_access_token": encrypt_token("some-tok")}
    stale_row = {
        "id": "pi-stale",
        "creator_id": "creator-1",
        "media_url": "https://cdn.instagram.com/reel.mp4",  # broken: raw video, not a thumbnail
        "post_link": IG_MEDIA[0]["permalink"],
        "media_type": "video",
        "like_count": 0,
        "comment_count": 0,
        "created_at": "2025-01-01T00:00:00+00:00",
    }
    repo = FakeCreatorRepo(creator=connected, existing_portfolio=[stale_row])

    items = await creator_service.import_instagram_portfolio(profile_id="profile-1", repo=repo)

    assert len(items) == 1
    assert items[0]["id"] == "pi-stale"
    assert repo.portfolio_inserted == []
    assert len(repo.portfolio_updated) == 1
    updated_id, updated_data = repo.portfolio_updated[0]
    assert updated_id == "pi-stale"
    assert updated_data["media_url"] == "https://cdn.instagram.com/reel-thumb.jpg"


async def test_preview_instagram_media_does_not_insert_anything(monkeypatch):
    _patch_instagram_service(monkeypatch)
    connected = {**CREATOR_ROW, "instagram_access_token": encrypt_token("some-tok")}
    repo = FakeCreatorRepo(creator=connected)

    items = await creator_service.preview_instagram_media(profile_id="profile-1", repo=repo)

    assert len(items) == 1
    assert items[0]["id"] == IG_MEDIA[0]["id"]
    assert items[0]["media_url"] == IG_MEDIA[0]["media_url"]
    assert items[0]["media_type"] == "video"
    assert repo.portfolio_inserted is None  # preview never writes to the portfolio


async def test_preview_instagram_media_not_connected_422():
    repo = FakeCreatorRepo(creator=dict(CREATOR_ROW))

    with pytest.raises(HTTPException) as exc_info:
        await creator_service.preview_instagram_media(profile_id="profile-1", repo=repo)
    assert exc_info.value.status_code == 422


async def test_import_instagram_portfolio_imports_only_selected_media_ids(monkeypatch):
    _patch_instagram_service(monkeypatch)
    connected = {**CREATOR_ROW, "instagram_access_token": encrypt_token("some-tok")}
    repo = FakeCreatorRepo(creator=connected)

    items = await creator_service.import_instagram_portfolio(
        profile_id="profile-1", media_ids=[IG_MEDIA[0]["id"]], repo=repo
    )

    assert len(items) == 1
    assert repo.portfolio_inserted[0]["creator_id"] == "creator-1"


async def test_import_instagram_portfolio_filters_out_unselected_media_ids(monkeypatch):
    _patch_instagram_service(monkeypatch)
    connected = {**CREATOR_ROW, "instagram_access_token": encrypt_token("some-tok")}
    repo = FakeCreatorRepo(creator=connected)

    items = await creator_service.import_instagram_portfolio(
        profile_id="profile-1", media_ids=["some-other-id-not-in-media"], repo=repo
    )

    assert items == []
    assert repo.portfolio_inserted is None


async def test_import_instagram_portfolio_not_connected_422():
    repo = FakeCreatorRepo(creator=dict(CREATOR_ROW))

    with pytest.raises(HTTPException) as exc_info:
        await creator_service.import_instagram_portfolio(profile_id="profile-1", repo=repo)

    assert exc_info.value.status_code == 422


def test_to_public_row_reports_instagram_connected_from_user_id():
    """Regression: to_public_row previously stripped instagram_user_id (the
    only real 'is Instagram connected' signal) without replacing it with
    anything — clients were left with only the self-reported
    instagram_handle text field, which is set at signup regardless of
    whether Instagram was ever actually connected."""
    connected = _make_creator({**CREATOR_ROW, "instagram_user_id": "999"})
    not_connected = _make_creator(dict(CREATOR_ROW))

    assert connected.to_public_row()["instagram_connected"] is True
    assert not_connected.to_public_row()["instagram_connected"] is False
    assert "instagram_user_id" not in connected.to_public_row()
