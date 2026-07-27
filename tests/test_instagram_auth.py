"""
Unit tests for auth_service.instagram_auth — Instagram Graph API calls and
the Supabase admin/anon clients are faked, so no real network/DB calls happen.
"""

import pytest
from fastapi import HTTPException

from app.schemas.auth import InstagramAuthRequest
from app.services import auth_service

IG_PROFILE = {
    "user_id": 17841441112302348,
    "username": "kolablyofficial",
    "name": "Kolably",
    "biography": "Connect with nearby creators and run authentic collaborations",
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

EXISTING_PROFILE = {
    "id": "profile-ig-1",
    "auth_id": "auth-ig-1",
    "email": "alice@example.com",
    "role": "creator",
    "is_active": True,
}


class FakeAdminAuth:
    def __init__(self, create_user_response=None):
        self._create_user_response = create_user_response
        self.create_user_calls = []
        self.generate_link_calls = []

    async def create_user(self, attributes):
        self.create_user_calls.append(attributes)
        return self._create_user_response

    async def generate_link(self, params):
        self.generate_link_calls.append(params)
        return FakeGenerateLinkResponse()


class FakeLinkProperties:
    hashed_token = "hashed-token-abc"


class FakeGenerateLinkResponse:
    properties = FakeLinkProperties()


class FakeAdminGoTrue:
    def __init__(self, admin):
        self.admin = admin


class FakeAdminSupabaseClient:
    def __init__(self, admin):
        self.auth = FakeAdminGoTrue(admin)


class FakeSession:
    access_token = "ig-access-token"
    refresh_token = "ig-refresh-token"


class FakeAuthResponse:
    session = FakeSession()


class FakeAnonGoTrue:
    def __init__(self):
        self.verify_otp_calls = []

    async def verify_otp(self, params):
        self.verify_otp_calls.append(params)
        return FakeAuthResponse()


class FakeAnonSupabaseClient:
    def __init__(self):
        self.auth = FakeAnonGoTrue()


class FakeUser:
    def __init__(self, id="auth-new-1"):
        self.id = id


class FakeCreatorRepo:
    def __init__(self, existing=None):
        self._existing = existing
        self.inserted = None
        self.updated = None
        self.updated_profile_id = None
        self.portfolio_inserted = None

    async def get_by_instagram_user_id(self, instagram_user_id):
        return self._existing

    async def update_by_profile_id(self, profile_id, data):
        self.updated_profile_id = profile_id
        self.updated = data
        return {**data, "profile_id": profile_id}

    async def insert_creator(self, data):
        self.inserted = data
        return {**data, "id": "creator-ig-1"}

    async def insert_portfolio_items(self, items):
        self.portfolio_inserted = items
        return items


class FakeProfileRepo:
    def __init__(self, by_id=None, by_auth_id=None):
        self._by_id = by_id or {}
        self._by_auth_id = by_auth_id

    async def get_by_id(self, profile_id):
        return self._by_id.get(profile_id)

    async def get_by_auth_id(self, auth_id):
        return self._by_auth_id


def _patch_instagram_service(monkeypatch, media=IG_MEDIA, profile=IG_PROFILE):
    async def fake_exchange_code_for_token(code, redirect_uri):
        return {"access_token": "short-lived-tok", "user_id": "999"}

    async def fake_exchange_for_long_lived_token(short_lived_token):
        return {"access_token": "long-lived-tok", "expires_in": 5183854}

    async def fake_fetch_profile(access_token):
        return profile

    async def fake_fetch_media(access_token):
        return media

    async def fake_calculate_engagement_rate(access_token, media):
        return 12.5

    monkeypatch.setattr(auth_service.instagram_service, "exchange_code_for_token", fake_exchange_code_for_token)
    monkeypatch.setattr(
        auth_service.instagram_service, "exchange_for_long_lived_token", fake_exchange_for_long_lived_token
    )
    monkeypatch.setattr(auth_service.instagram_service, "fetch_profile", fake_fetch_profile)
    monkeypatch.setattr(auth_service.instagram_service, "fetch_media", fake_fetch_media)
    monkeypatch.setattr(auth_service.instagram_service, "calculate_engagement_rate", fake_calculate_engagement_rate)


def _patch_supabase(monkeypatch, admin_auth, anon_client=None):
    async def fake_get_supabase_admin_client():
        return FakeAdminSupabaseClient(admin_auth)

    async def fake_get_supabase_client():
        return anon_client or FakeAnonSupabaseClient()

    monkeypatch.setattr(auth_service, "get_supabase_admin_client", fake_get_supabase_admin_client)
    monkeypatch.setattr(auth_service, "get_supabase_client", fake_get_supabase_client)


async def test_instagram_auth_new_user_signup_prefills_everything(monkeypatch):
    _patch_instagram_service(monkeypatch)
    admin_auth = FakeAdminAuth(create_user_response=type("R", (), {"user": FakeUser()})())
    _patch_supabase(monkeypatch, admin_auth)

    creator_repo = FakeCreatorRepo(existing=None)
    profile_repo = FakeProfileRepo(by_auth_id={**EXISTING_PROFILE, "auth_id": "auth-new-1", "id": "profile-new-1"})

    result = await auth_service.instagram_auth(
        InstagramAuthRequest(code="auth-code", redirect_uri="http://localhost:8080/", role="creator"),
        profile_repo=profile_repo,
        creator_repo=creator_repo,
    )

    assert result["is_new_user"] is True
    assert result["access_token"] == "ig-access-token"

    # placeholder email used since Instagram never returns one
    assert admin_auth.create_user_calls[0]["email"] == "ig_17841441112302348@users.kolably.instagram"
    assert admin_auth.create_user_calls[0]["user_metadata"] == {"role": "creator"}

    assert creator_repo.inserted["name"] == "Kolably"
    assert creator_repo.inserted["bio"] == IG_PROFILE["biography"]
    assert creator_repo.inserted["website"] == IG_PROFILE["website"]
    assert creator_repo.inserted["follower_count"] == 304
    assert creator_repo.inserted["following_count"] == 5
    assert creator_repo.inserted["engagement_rate"] == 12.5
    assert creator_repo.inserted["instagram_user_id"] == "17841441112302348"
    assert creator_repo.inserted["instagram_access_token"] != "long-lived-tok"  # encrypted, not raw

    assert creator_repo.portfolio_inserted == [
        {
            "creator_id": "creator-ig-1",
            "media_url": IG_MEDIA[0]["media_url"],
            "post_link": IG_MEDIA[0]["permalink"],
            "media_type": "video",
            "like_count": 1,
            "comment_count": 0,
        }
    ]


async def test_instagram_auth_new_user_requires_creator_role(monkeypatch):
    _patch_instagram_service(monkeypatch)
    _patch_supabase(monkeypatch, FakeAdminAuth())
    creator_repo = FakeCreatorRepo(existing=None)

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.instagram_auth(
            InstagramAuthRequest(code="auth-code", redirect_uri="http://localhost:8080/"),
            creator_repo=creator_repo,
        )

    assert exc_info.value.status_code == 400
    assert creator_repo.inserted is None


async def test_instagram_auth_returning_user_refreshes_stats_only(monkeypatch):
    _patch_instagram_service(monkeypatch)
    _patch_supabase(monkeypatch, FakeAdminAuth())

    existing_creator = {"profile_id": "profile-existing-1", "instagram_user_id": "17841441112302348"}
    creator_repo = FakeCreatorRepo(existing=existing_creator)
    profile_repo = FakeProfileRepo(by_id={"profile-existing-1": dict(EXISTING_PROFILE)})

    result = await auth_service.instagram_auth(
        InstagramAuthRequest(code="auth-code", redirect_uri="http://localhost:8080/"),
        profile_repo=profile_repo,
        creator_repo=creator_repo,
    )

    assert result["is_new_user"] is False
    assert result["user"]["email"] == "alice@example.com"
    assert creator_repo.inserted is None  # no new creator row
    assert creator_repo.updated_profile_id == "profile-existing-1"
    assert creator_repo.updated["follower_count"] == 304
    assert creator_repo.updated["following_count"] == 5
    assert "name" not in creator_repo.updated  # connect-once fields untouched on resync
    assert "bio" not in creator_repo.updated


async def test_instagram_auth_returning_deactivated_account(monkeypatch):
    _patch_instagram_service(monkeypatch)
    _patch_supabase(monkeypatch, FakeAdminAuth())

    existing_creator = {"profile_id": "profile-existing-1", "instagram_user_id": "17841441112302348"}
    creator_repo = FakeCreatorRepo(existing=existing_creator)
    profile_repo = FakeProfileRepo(by_id={"profile-existing-1": {**EXISTING_PROFILE, "is_active": False}})

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.instagram_auth(
            InstagramAuthRequest(code="auth-code", redirect_uri="http://localhost:8080/"),
            profile_repo=profile_repo,
            creator_repo=creator_repo,
        )

    assert exc_info.value.status_code == 403
