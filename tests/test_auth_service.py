"""
Unit tests for auth_service.google_auth — Supabase client and repositories
are faked, so no real network/DB calls happen.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from supabase_auth.errors import AuthApiError

from app.schemas.auth import GoogleAuthRequest
from app.services import auth_service

NOW = datetime(2026, 7, 26, 12, 0, 0, tzinfo=UTC)

PROFILE = {
    "id": "profile-1",
    "auth_id": "auth-1",
    "email": "alice@example.com",
    "role": "creator",
    "is_active": True,
}


class FakeUser:
    def __init__(self, created_at, last_sign_in_at, user_metadata=None, id="auth-1"):
        self.id = id
        self.created_at = created_at
        self.last_sign_in_at = last_sign_in_at
        self.user_metadata = user_metadata or {}


class FakeSession:
    access_token = "access-token"
    refresh_token = "refresh-token"


class FakeAuthResponse:
    def __init__(self, user, session):
        self.user = user
        self.session = session


class FakeGoTrue:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.last_credentials = None

    async def sign_in_with_id_token(self, credentials):
        self.last_credentials = credentials
        if self._error:
            raise self._error
        return self._response


class FakeSupabaseClient:
    def __init__(self, gotrue):
        self.auth = gotrue


class FakeProfileRepo:
    def __init__(self, profile):
        self._profile = profile
        self.update_role_calls = []

    async def get_by_auth_id(self, auth_id):
        return self._profile

    async def update_role(self, profile_id, role):
        self.update_role_calls.append((profile_id, role))
        self._profile = {**self._profile, "role": role}
        return self._profile


class FakeCreatorRepo:
    def __init__(self):
        self.inserted = None

    async def insert_creator(self, data):
        self.inserted = data
        return {**data, "id": "creator-1"}


class FakeBusinessRepo:
    def __init__(self):
        self.inserted = None

    async def insert_business(self, data):
        self.inserted = data
        return {**data, "id": "business-1"}


def _patch_supabase(monkeypatch, gotrue):
    async def fake_get_supabase_client():
        return FakeSupabaseClient(gotrue)

    monkeypatch.setattr(auth_service, "get_supabase_client", fake_get_supabase_client)


async def test_google_auth_returning_user_logs_in(monkeypatch):
    user = FakeUser(created_at=NOW - timedelta(days=30), last_sign_in_at=NOW)
    _patch_supabase(monkeypatch, FakeGoTrue(response=FakeAuthResponse(user, FakeSession())))
    profile_repo = FakeProfileRepo(dict(PROFILE))
    creator_repo = FakeCreatorRepo()
    business_repo = FakeBusinessRepo()

    result = await auth_service.google_auth(
        GoogleAuthRequest(id_token="tok"),
        profile_repo=profile_repo,
        creator_repo=creator_repo,
        business_repo=business_repo,
    )

    assert result["is_new_user"] is False
    assert result["access_token"] == "access-token"
    assert result["user"]["id"] == "profile-1"
    assert profile_repo.update_role_calls == []
    assert creator_repo.inserted is None
    assert business_repo.inserted is None


async def test_google_auth_new_user_requires_role(monkeypatch):
    user = FakeUser(created_at=NOW, last_sign_in_at=NOW)
    _patch_supabase(monkeypatch, FakeGoTrue(response=FakeAuthResponse(user, FakeSession())))
    profile_repo = FakeProfileRepo(dict(PROFILE))

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.google_auth(
            GoogleAuthRequest(id_token="tok"),
            profile_repo=profile_repo,
            creator_repo=FakeCreatorRepo(),
            business_repo=FakeBusinessRepo(),
        )

    assert exc_info.value.status_code == 400


async def test_google_auth_new_creator_uses_default_role_no_reassignment(monkeypatch):
    user = FakeUser(
        created_at=NOW,
        last_sign_in_at=NOW,
        user_metadata={"full_name": "Alice Creator", "avatar_url": "https://img/alice.png"},
    )
    _patch_supabase(monkeypatch, FakeGoTrue(response=FakeAuthResponse(user, FakeSession())))
    profile_repo = FakeProfileRepo(dict(PROFILE))  # role already 'creator'
    creator_repo = FakeCreatorRepo()
    business_repo = FakeBusinessRepo()

    result = await auth_service.google_auth(
        GoogleAuthRequest(id_token="tok", role="creator"),
        profile_repo=profile_repo,
        creator_repo=creator_repo,
        business_repo=business_repo,
    )

    assert result["is_new_user"] is True
    assert profile_repo.update_role_calls == []
    assert creator_repo.inserted == {
        "profile_id": "profile-1",
        "name": "Alice Creator",
        "profile_photo_url": "https://img/alice.png",
    }
    assert business_repo.inserted is None


async def test_google_auth_new_business_reassigns_role_and_creates_row(monkeypatch):
    user = FakeUser(
        created_at=NOW,
        last_sign_in_at=NOW,
        user_metadata={"name": "Bob Biz", "picture": "https://img/bob.png"},
    )
    _patch_supabase(monkeypatch, FakeGoTrue(response=FakeAuthResponse(user, FakeSession())))
    profile_repo = FakeProfileRepo(dict(PROFILE))  # default role 'creator', wants 'business'
    creator_repo = FakeCreatorRepo()
    business_repo = FakeBusinessRepo()

    result = await auth_service.google_auth(
        GoogleAuthRequest(id_token="tok", role="business"),
        profile_repo=profile_repo,
        creator_repo=creator_repo,
        business_repo=business_repo,
    )

    assert result["is_new_user"] is True
    assert result["user"]["role"] == "business"
    assert profile_repo.update_role_calls == [("profile-1", "business")]
    assert business_repo.inserted == {
        "profile_id": "profile-1",
        "business_name": "Bob Biz",
        "logo_url": "https://img/bob.png",
    }
    assert creator_repo.inserted is None


async def test_google_auth_deactivated_account(monkeypatch):
    user = FakeUser(created_at=NOW - timedelta(days=30), last_sign_in_at=NOW)
    _patch_supabase(monkeypatch, FakeGoTrue(response=FakeAuthResponse(user, FakeSession())))
    profile_repo = FakeProfileRepo({**PROFILE, "is_active": False})

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.google_auth(
            GoogleAuthRequest(id_token="tok"),
            profile_repo=profile_repo,
            creator_repo=FakeCreatorRepo(),
            business_repo=FakeBusinessRepo(),
        )

    assert exc_info.value.status_code == 403


async def test_google_auth_invalid_token_raises_401(monkeypatch):
    _patch_supabase(
        monkeypatch,
        FakeGoTrue(error=AuthApiError("invalid token", 400, None)),
    )

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.google_auth(GoogleAuthRequest(id_token="bad-tok"))

    assert exc_info.value.status_code == 401


async def test_google_auth_forwards_nonce_when_provided(monkeypatch):
    """Regression: the frontend hashes a nonce into the GIS config, so the
    same raw nonce must reach Supabase or it rejects the token with
    'Passed nonce and nonce in id_token should either both exist or not.'"""
    user = FakeUser(created_at=NOW - timedelta(days=30), last_sign_in_at=NOW)
    gotrue = FakeGoTrue(response=FakeAuthResponse(user, FakeSession()))
    _patch_supabase(monkeypatch, gotrue)

    await auth_service.google_auth(
        GoogleAuthRequest(id_token="tok", nonce="raw-nonce-value"),
        profile_repo=FakeProfileRepo(dict(PROFILE)),
        creator_repo=FakeCreatorRepo(),
        business_repo=FakeBusinessRepo(),
    )

    assert gotrue.last_credentials == {
        "provider": "google",
        "token": "tok",
        "nonce": "raw-nonce-value",
    }


class FakeAdminAuthForLogout:
    def __init__(self, error=None):
        self._error = error
        self.sign_out_calls = []

    async def sign_out(self, jwt, scope):
        self.sign_out_calls.append((jwt, scope))
        if self._error:
            raise self._error


def _patch_admin_supabase_for_logout(monkeypatch, admin_auth):
    class FakeAdminGoTrue:
        def __init__(self, admin):
            self.admin = admin

    class FakeAdminSupabaseClient:
        def __init__(self, admin):
            self.auth = FakeAdminGoTrue(admin)

    async def fake_get_supabase_admin_client():
        return FakeAdminSupabaseClient(admin_auth)

    monkeypatch.setattr(auth_service, "get_supabase_admin_client", fake_get_supabase_admin_client)


async def test_logout_revokes_token_via_admin_sign_out(monkeypatch):
    """Regression: auth.sign_out() takes no token arg and only signs out the
    client's own (always empty) session — admin.sign_out(jwt, scope) is the
    one that actually revokes an arbitrary token."""
    admin_auth = FakeAdminAuthForLogout()
    _patch_admin_supabase_for_logout(monkeypatch, admin_auth)

    result = await auth_service.logout("some-access-token")

    assert result == {"message": "Logged out successfully"}
    assert admin_auth.sign_out_calls == [("some-access-token", "global")]


async def test_logout_swallows_auth_api_error(monkeypatch):
    admin_auth = FakeAdminAuthForLogout(error=AuthApiError("invalid token", 401, None))
    _patch_admin_supabase_for_logout(monkeypatch, admin_auth)

    result = await auth_service.logout("already-expired-token")

    assert result == {"message": "Logged out successfully"}


async def test_google_auth_omits_nonce_when_not_provided(monkeypatch):
    user = FakeUser(created_at=NOW - timedelta(days=30), last_sign_in_at=NOW)
    gotrue = FakeGoTrue(response=FakeAuthResponse(user, FakeSession()))
    _patch_supabase(monkeypatch, gotrue)

    await auth_service.google_auth(
        GoogleAuthRequest(id_token="tok"),
        profile_repo=FakeProfileRepo(dict(PROFILE)),
        creator_repo=FakeCreatorRepo(),
        business_repo=FakeBusinessRepo(),
    )

    assert "nonce" not in gotrue.last_credentials
