"""
Unit tests for auth_service.google_auth — Supabase client and repositories
are faked, so no real network/DB calls happen.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from supabase_auth.errors import AuthApiError

from app.models.user import UserProfile
from app.schemas.auth import BusinessSignupRequest, CreatorSignupRequest, GoogleAuthRequest
from app.services import auth_service

NOW = datetime(2026, 7, 26, 12, 0, 0, tzinfo=UTC)

PROFILE = {
    "id": "profile-1",
    "auth_id": "auth-1",
    "email": "alice@example.com",
    "role": "creator",
    "is_active": True,
}


def _make_profile(data: dict) -> UserProfile:
    """Build a UserProfile model from a raw dict (mirrors repo from_row)."""
    from app.core.enums import UserRole

    return UserProfile(
        id=data["id"],
        auth_id=data["auth_id"],
        email=data["email"],
        role=UserRole(data["role"]),
        is_active=data.get("is_active", True),
        created_at=data.get("created_at", NOW),
    )


class FakeUser:
    def __init__(
        self,
        created_at,
        last_sign_in_at,
        user_metadata=None,
        id="auth-1",
        email_confirmed_at=NOW,
        identities=None,
    ):
        self.id = id
        self.created_at = created_at
        self.last_sign_in_at = last_sign_in_at
        self.user_metadata = user_metadata or {}
        # Defaults truthy (confirmed) so every existing google_auth test —
        # none of which exercise email confirmation — keeps passing
        # unchanged; signup tests override it explicitly.
        self.email_confirmed_at = email_confirmed_at
        # A real signup always comes back with exactly one identity; an
        # empty list is Supabase's tell for "this email is already
        # registered" (see auth_service._is_repeated_signup). Defaults to
        # the one-identity shape so existing tests keep describing genuine
        # signups.
        self.identities = [object()] if identities is None else identities


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
        self.last_reset_password_call = None
        self.last_resend_call = None

    async def sign_in_with_id_token(self, credentials):
        self.last_credentials = credentials
        if self._error:
            raise self._error
        return self._response

    async def sign_up(self, credentials):
        self.last_credentials = credentials
        if self._error:
            raise self._error
        return self._response

    async def verify_otp(self, credentials):
        self.last_credentials = credentials
        if self._error:
            raise self._error
        return self._response

    async def reset_password_email(self, email, options=None):
        self.last_reset_password_call = (email, options)
        if self._error:
            raise self._error

    async def resend(self, params):
        self.last_resend_call = params
        if self._error:
            raise self._error


class FakeSupabaseClient:
    def __init__(self, gotrue):
        self.auth = gotrue


class FakeProfileRepo:
    def __init__(self, profile):
        self._profile = profile
        self.update_role_calls = []

    async def get_by_auth_id(self, auth_id):
        return _make_profile(self._profile)

    async def update_role(self, profile_id, role):
        self.update_role_calls.append((profile_id, role))
        self._profile = {**self._profile, "role": role}
        return _make_profile(self._profile)


class FakeCreatorRepo:
    def __init__(self, creator=None):
        self.inserted = None
        self._creator = creator

    async def insert_creator(self, data):
        self.inserted = data
        return {**data, "id": "creator-1"}

    async def get_by_profile_id(self, profile_id):
        return self._creator


class FakeBusinessRepo:
    def __init__(self, business=None):
        self.inserted = None
        self._business = business

    async def insert_business(self, data):
        self.inserted = data
        return {**data, "id": "business-1"}

    async def get_by_profile_id(self, profile_id):
        return self._business


async def _none(*args, **kwargs):
    """Awaitable None — for stubbing a repo lookup that has to miss."""
    return None


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


async def test_forgot_password_defaults_to_web_redirect_when_none_given(monkeypatch):
    """Regression: with no redirect_to, Supabase falls back to the project's
    dashboard Site URL — a stale localhost value, so recovery links opened
    anywhere landed on a dead page instead of a real destination. The web
    URL is the safe default since it works with or without the mobile app."""
    from app.core.config import settings

    gotrue = FakeGoTrue()
    _patch_supabase(monkeypatch, gotrue)

    result = await auth_service.forgot_password("alice@example.com")

    assert result == {"message": "Password reset link sent to your email"}
    assert gotrue.last_reset_password_call == (
        "alice@example.com",
        {"redirect_to": settings.WEB_PASSWORD_RESET_REDIRECT_URL},
    )


async def test_forgot_password_uses_mobile_redirect_when_requested(monkeypatch):
    from app.core.config import settings

    gotrue = FakeGoTrue()
    _patch_supabase(monkeypatch, gotrue)

    await auth_service.forgot_password(
        "alice@example.com", redirect_to=settings.MOBILE_PASSWORD_RESET_REDIRECT_URL
    )

    assert gotrue.last_reset_password_call == (
        "alice@example.com",
        {"redirect_to": settings.MOBILE_PASSWORD_RESET_REDIRECT_URL},
    )


async def test_forgot_password_ignores_unrecognized_redirect_to(monkeypatch):
    """An arbitrary caller-supplied redirect_to must never be forwarded as-is
    — otherwise this endpoint becomes an open redirect for the recovery
    link. Falls back to the web URL just like the no-redirect_to case."""
    from app.core.config import settings

    gotrue = FakeGoTrue()
    _patch_supabase(monkeypatch, gotrue)

    await auth_service.forgot_password(
        "alice@example.com", redirect_to="https://evil.example.com/phish"
    )

    assert gotrue.last_reset_password_call == (
        "alice@example.com",
        {"redirect_to": settings.WEB_PASSWORD_RESET_REDIRECT_URL},
    )


async def test_forgot_password_raises_400_on_auth_api_error(monkeypatch):
    gotrue = FakeGoTrue(error=AuthApiError("rate limited", 429, None))
    _patch_supabase(monkeypatch, gotrue)

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.forgot_password("alice@example.com")

    assert exc_info.value.status_code == 400


# ── signup_creator / signup_business: email confirmation gate ─────────
#
# Regression coverage for a real gap: sign_up() was trusted to only return
# a session for a confirmed user (per auth_implementation.md §6.2), but
# that's actually a property of the Supabase project's own "Confirm email"
# setting — with it off, sign_up() hands back a full session immediately
# regardless of confirmation, and the old code forwarded it unconditionally,
# letting anyone in with zero proof they own the email they signed up with.

CREATOR_SIGNUP_DATA = CreatorSignupRequest(
    name="Alice",
    username="alice",
    email="alice@example.com",
    password="Password123",
    city="Springfield",
    niche="food",
)

BUSINESS_SIGNUP_DATA = BusinessSignupRequest(
    name="Bob Biz",
    email="bob@example.com",
    password="Password123",
)


async def test_signup_creator_withholds_tokens_when_email_unconfirmed(monkeypatch):
    """The exact real-world bug: Supabase's 'Confirm email' setting is off,
    so sign_up() returns a real session immediately even though the user
    hasn't proven anything. The response must not carry that session."""
    user = FakeUser(created_at=NOW, last_sign_in_at=NOW, email_confirmed_at=None)
    _patch_supabase(monkeypatch, FakeGoTrue(response=FakeAuthResponse(user, FakeSession())))

    result = await auth_service.signup_creator(
        CREATOR_SIGNUP_DATA,
        profile_repo=FakeProfileRepo(dict(PROFILE)),
        creator_repo=FakeCreatorRepo(),
    )

    assert result["access_token"] is None
    assert result["refresh_token"] is None


async def test_signup_creator_returns_tokens_when_email_confirmed(monkeypatch):
    """If the account genuinely is pre-confirmed (e.g. an admin-created
    account, or 'Confirm email' legitimately off by design for a given
    flow), a real session is still returned — this isn't a blanket ban on
    signup returning a session, only on trusting an unconfirmed one."""
    user = FakeUser(created_at=NOW, last_sign_in_at=NOW, email_confirmed_at=NOW)
    _patch_supabase(monkeypatch, FakeGoTrue(response=FakeAuthResponse(user, FakeSession())))

    result = await auth_service.signup_creator(
        CREATOR_SIGNUP_DATA,
        profile_repo=FakeProfileRepo(dict(PROFILE)),
        creator_repo=FakeCreatorRepo(),
    )

    assert result["access_token"] == "access-token"
    assert result["refresh_token"] == "refresh-token"


async def test_signup_creator_no_session_at_all_still_withholds_tokens(monkeypatch):
    """The 'normal', intended case: Supabase itself declines to issue a
    session for an unconfirmed signup. Confirms the fix doesn't regress
    the already-correct path."""
    user = FakeUser(created_at=NOW, last_sign_in_at=NOW, email_confirmed_at=None)
    _patch_supabase(monkeypatch, FakeGoTrue(response=FakeAuthResponse(user, None)))

    result = await auth_service.signup_creator(
        CREATOR_SIGNUP_DATA,
        profile_repo=FakeProfileRepo(dict(PROFILE)),
        creator_repo=FakeCreatorRepo(),
    )

    assert result["access_token"] is None
    assert result["refresh_token"] is None


async def test_signup_business_withholds_tokens_when_email_unconfirmed(monkeypatch):
    user = FakeUser(created_at=NOW, last_sign_in_at=NOW, email_confirmed_at=None)
    _patch_supabase(monkeypatch, FakeGoTrue(response=FakeAuthResponse(user, FakeSession())))

    result = await auth_service.signup_business(
        BUSINESS_SIGNUP_DATA,
        profile_repo=FakeProfileRepo({**PROFILE, "role": "business"}),
        business_repo=FakeBusinessRepo(),
    )

    assert result["access_token"] is None
    assert result["refresh_token"] is None


async def test_signup_business_returns_tokens_when_email_confirmed(monkeypatch):
    user = FakeUser(created_at=NOW, last_sign_in_at=NOW, email_confirmed_at=NOW)
    _patch_supabase(monkeypatch, FakeGoTrue(response=FakeAuthResponse(user, FakeSession())))

    result = await auth_service.signup_business(
        BUSINESS_SIGNUP_DATA,
        profile_repo=FakeProfileRepo({**PROFILE, "role": "business"}),
        business_repo=FakeBusinessRepo(),
    )

    assert result["access_token"] == "access-token"
    assert result["refresh_token"] == "refresh-token"


# ── signup_creator / signup_business: confirmation-link redirect_to ───
#
# Regression: the confirmation email's link always pointed at the web app
# regardless of which platform someone signed up on — a mobile signup whose
# link opened a browser instead of returning to the app, with no way back
# except stumbling onto "forgot password" on the web login page. Mirrors the
# same web/mobile allow-list forgot_password already has.

async def test_signup_creator_defaults_to_web_redirect_when_none_given(monkeypatch):
    from app.core.config import settings

    user = FakeUser(created_at=NOW, last_sign_in_at=NOW, email_confirmed_at=NOW)
    gotrue = FakeGoTrue(response=FakeAuthResponse(user, FakeSession()))
    _patch_supabase(monkeypatch, gotrue)

    await auth_service.signup_creator(
        CREATOR_SIGNUP_DATA,
        profile_repo=FakeProfileRepo(dict(PROFILE)),
        creator_repo=FakeCreatorRepo(),
    )

    assert gotrue.last_credentials["options"]["email_redirect_to"] == settings.WEB_SIGNUP_CONFIRM_REDIRECT_URL


async def test_signup_creator_uses_mobile_redirect_when_requested(monkeypatch):
    from app.core.config import settings

    user = FakeUser(created_at=NOW, last_sign_in_at=NOW, email_confirmed_at=NOW)
    gotrue = FakeGoTrue(response=FakeAuthResponse(user, FakeSession()))
    _patch_supabase(monkeypatch, gotrue)

    mobile_signup = CREATOR_SIGNUP_DATA.model_copy(
        update={"redirect_to": settings.MOBILE_SIGNUP_CONFIRM_REDIRECT_URL}
    )
    await auth_service.signup_creator(
        mobile_signup,
        profile_repo=FakeProfileRepo(dict(PROFILE)),
        creator_repo=FakeCreatorRepo(),
    )

    assert gotrue.last_credentials["options"]["email_redirect_to"] == settings.MOBILE_SIGNUP_CONFIRM_REDIRECT_URL


async def test_signup_creator_ignores_unrecognized_redirect_to(monkeypatch):
    """An arbitrary caller-supplied redirect_to must never be forwarded as-is
    — otherwise signup becomes an open redirect for the confirmation link."""
    from app.core.config import settings

    user = FakeUser(created_at=NOW, last_sign_in_at=NOW, email_confirmed_at=NOW)
    gotrue = FakeGoTrue(response=FakeAuthResponse(user, FakeSession()))
    _patch_supabase(monkeypatch, gotrue)

    phishy_signup = CREATOR_SIGNUP_DATA.model_copy(
        update={"redirect_to": "https://evil.example.com/phish"}
    )
    await auth_service.signup_creator(
        phishy_signup,
        profile_repo=FakeProfileRepo(dict(PROFILE)),
        creator_repo=FakeCreatorRepo(),
    )

    assert gotrue.last_credentials["options"]["email_redirect_to"] == settings.WEB_SIGNUP_CONFIRM_REDIRECT_URL


async def test_signup_business_uses_mobile_redirect_when_requested(monkeypatch):
    from app.core.config import settings

    user = FakeUser(created_at=NOW, last_sign_in_at=NOW, email_confirmed_at=NOW)
    gotrue = FakeGoTrue(response=FakeAuthResponse(user, FakeSession()))
    _patch_supabase(monkeypatch, gotrue)

    mobile_signup = BUSINESS_SIGNUP_DATA.model_copy(
        update={"redirect_to": settings.MOBILE_SIGNUP_CONFIRM_REDIRECT_URL}
    )
    await auth_service.signup_business(
        mobile_signup,
        profile_repo=FakeProfileRepo({**PROFILE, "role": "business"}),
        business_repo=FakeBusinessRepo(),
    )

    assert gotrue.last_credentials["options"]["email_redirect_to"] == settings.MOBILE_SIGNUP_CONFIRM_REDIRECT_URL


async def test_resend_verification_email_uses_mobile_redirect_when_requested(monkeypatch):
    from app.core.config import settings

    gotrue = FakeGoTrue()
    _patch_supabase(monkeypatch, gotrue)

    await auth_service.resend_verification_email(
        "alice@example.com", redirect_to=settings.MOBILE_SIGNUP_CONFIRM_REDIRECT_URL
    )

    assert gotrue.last_resend_call == (
        {
            "type": "signup",
            "email": "alice@example.com",
            "options": {"email_redirect_to": settings.MOBILE_SIGNUP_CONFIRM_REDIRECT_URL},
        }
    )


async def test_resend_verification_email_defaults_to_web_redirect(monkeypatch):
    from app.core.config import settings

    gotrue = FakeGoTrue()
    _patch_supabase(monkeypatch, gotrue)

    await auth_service.resend_verification_email("alice@example.com")

    assert gotrue.last_resend_call["options"]["email_redirect_to"] == settings.WEB_SIGNUP_CONFIRM_REDIRECT_URL


# ── signup_creator / signup_business: duplicate-signup guard ──────────
#
# Regression coverage for a real production 500: sign_up() doesn't error
# for an email that's already registered — Supabase returns HTTP 200 with
# that account's real user id and no session (logged in the Supabase
# dashboard as "user_repeated_signup"), by design, so this endpoint can't
# be used to enumerate registered emails. The old code inserted a
# creator/business row unconditionally, which hit creators_profile_id_key /
# businesses_profile_id_key's unique constraint on a second attempt and
# 500'd instead of giving a real answer.

EXISTING_CREATOR = {"id": "creator-1", "profile_id": "profile-1", "name": "Alice"}
EXISTING_BUSINESS = {"id": "business-1", "profile_id": "profile-1", "owner_name": "Bob Biz"}


async def test_signup_creator_sanitized_repeat_returns_409_not_500(monkeypatch):
    """The actual production 500. For an already-registered *confirmed*
    email, GoTrue returns 200 with a sanitized user: a random id that
    matches no profile row, email_confirmed_at nulled, and — the only
    reliable tell — an empty identities list. Looking that random id up
    hit the "Profile creation trigger failed" 500, which is what surfaced
    to the user as "our servers are having trouble"."""
    user = FakeUser(
        created_at=NOW,
        last_sign_in_at=NOW,
        id="random-uuid-matching-no-profile",
        email_confirmed_at=None,
        identities=[],
    )
    _patch_supabase(monkeypatch, FakeGoTrue(response=FakeAuthResponse(user, None)))
    # Deliberately returns None for any lookup — mirrors the real repo
    # finding nothing for the sanitized id.
    profile_repo = FakeProfileRepo(dict(PROFILE))
    profile_repo.get_by_auth_id = lambda auth_id: _none()

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.signup_creator(
            CREATOR_SIGNUP_DATA,
            profile_repo=profile_repo,
            creator_repo=FakeCreatorRepo(),
        )

    assert exc_info.value.status_code == 409
    assert "already exists" in exc_info.value.detail


async def test_signup_business_sanitized_repeat_returns_409_not_500(monkeypatch):
    user = FakeUser(
        created_at=NOW,
        last_sign_in_at=NOW,
        id="random-uuid-matching-no-profile",
        email_confirmed_at=None,
        identities=[],
    )
    _patch_supabase(monkeypatch, FakeGoTrue(response=FakeAuthResponse(user, None)))
    profile_repo = FakeProfileRepo({**PROFILE, "role": "business"})
    profile_repo.get_by_auth_id = lambda auth_id: _none()

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.signup_business(
            BUSINESS_SIGNUP_DATA,
            profile_repo=profile_repo,
            business_repo=FakeBusinessRepo(),
        )

    assert exc_info.value.status_code == 409


async def test_signup_creator_genuine_signup_not_treated_as_repeat(monkeypatch):
    """Guard against the check being too eager: a real first-time signup
    carries one identity and must still create the creator row."""
    user = FakeUser(created_at=NOW, last_sign_in_at=NOW, email_confirmed_at=None)
    _patch_supabase(monkeypatch, FakeGoTrue(response=FakeAuthResponse(user, None)))
    creator_repo = FakeCreatorRepo()

    result = await auth_service.signup_creator(
        CREATOR_SIGNUP_DATA,
        profile_repo=FakeProfileRepo(dict(PROFILE)),
        creator_repo=creator_repo,
    )

    assert result["access_token"] is None
    assert creator_repo.inserted is not None
    assert creator_repo.inserted["name"] == "Alice"


async def test_signup_creator_conflicts_when_already_registered_and_confirmed(monkeypatch):
    user = FakeUser(created_at=NOW, last_sign_in_at=NOW, email_confirmed_at=NOW)
    _patch_supabase(monkeypatch, FakeGoTrue(response=FakeAuthResponse(user, None)))
    creator_repo = FakeCreatorRepo(creator=EXISTING_CREATOR)

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.signup_creator(
            CREATOR_SIGNUP_DATA,
            profile_repo=FakeProfileRepo(dict(PROFILE)),
            creator_repo=creator_repo,
        )

    assert exc_info.value.status_code == 409
    assert creator_repo.inserted is None  # never attempted the doomed insert


async def test_signup_creator_repeat_attempt_while_still_unconfirmed_does_not_crash(monkeypatch):
    """Someone re-submitting signup before finishing verification — not a
    real conflict, just retry. Must not attempt a second insert (which
    would also 500), and must still respond like a normal signup so the
    frontend sends them back to the verify-email screen."""
    user = FakeUser(created_at=NOW, last_sign_in_at=NOW, email_confirmed_at=None)
    _patch_supabase(monkeypatch, FakeGoTrue(response=FakeAuthResponse(user, None)))
    creator_repo = FakeCreatorRepo(creator=EXISTING_CREATOR)

    result = await auth_service.signup_creator(
        CREATOR_SIGNUP_DATA,
        profile_repo=FakeProfileRepo(dict(PROFILE)),
        creator_repo=creator_repo,
    )

    assert result["access_token"] is None
    assert creator_repo.inserted is None


async def test_signup_business_conflicts_when_already_registered_and_confirmed(monkeypatch):
    user = FakeUser(created_at=NOW, last_sign_in_at=NOW, email_confirmed_at=NOW)
    _patch_supabase(monkeypatch, FakeGoTrue(response=FakeAuthResponse(user, None)))
    business_repo = FakeBusinessRepo(business=EXISTING_BUSINESS)

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.signup_business(
            BUSINESS_SIGNUP_DATA,
            profile_repo=FakeProfileRepo({**PROFILE, "role": "business"}),
            business_repo=business_repo,
        )

    assert exc_info.value.status_code == 409
    assert business_repo.inserted is None


async def test_signup_business_repeat_attempt_while_still_unconfirmed_does_not_crash(monkeypatch):
    user = FakeUser(created_at=NOW, last_sign_in_at=NOW, email_confirmed_at=None)
    _patch_supabase(monkeypatch, FakeGoTrue(response=FakeAuthResponse(user, None)))
    business_repo = FakeBusinessRepo(business=EXISTING_BUSINESS)

    result = await auth_service.signup_business(
        BUSINESS_SIGNUP_DATA,
        profile_repo=FakeProfileRepo({**PROFILE, "role": "business"}),
        business_repo=business_repo,
    )

    assert result["access_token"] is None
    assert business_repo.inserted is None


# ── verify_signup_otp ───────────────────────────────────────────────
#
# OTP was chosen over the confirmation link specifically because it works
# the same regardless of platform — see auth_service.verify_signup_otp's
# docstring. These cover the code being right, wrong, and the response
# shape actually carrying enough user data to render a name (a thinner
# shape here would've silently reintroduced the blank-name bug fixed
# earlier via normalizeAuthUser's fallback chain).


async def test_verify_signup_otp_success_returns_full_session_and_profile(monkeypatch):
    user = FakeUser(created_at=NOW, last_sign_in_at=NOW, email_confirmed_at=NOW)
    _patch_supabase(monkeypatch, FakeGoTrue(response=FakeAuthResponse(user, FakeSession())))

    result = await auth_service.verify_signup_otp(
        "alice@example.com",
        "123456",
        profile_repo=FakeProfileRepo(dict(PROFILE)),
        creator_repo=FakeCreatorRepo(),
        business_repo=FakeBusinessRepo(),
    )

    assert result["access_token"] == "access-token"
    assert result["refresh_token"] == "refresh-token"
    assert result["user"]["id"] == "profile-1"
    assert result["user"]["email"] == "alice@example.com"


async def test_verify_signup_otp_forwards_email_and_type(monkeypatch):
    """Regression: type must be 'signup' — verify_otp also handles
    'recovery'/'email_change' etc., and sending the wrong type rejects a
    perfectly valid code."""
    user = FakeUser(created_at=NOW, last_sign_in_at=NOW, email_confirmed_at=NOW)
    gotrue = FakeGoTrue(response=FakeAuthResponse(user, FakeSession()))
    _patch_supabase(monkeypatch, gotrue)

    await auth_service.verify_signup_otp(
        "alice@example.com",
        "123456",
        profile_repo=FakeProfileRepo(dict(PROFILE)),
        creator_repo=FakeCreatorRepo(),
        business_repo=FakeBusinessRepo(),
    )

    assert gotrue.last_credentials == {
        "email": "alice@example.com",
        "token": "123456",
        "type": "signup",
    }


async def test_verify_signup_otp_invalid_code_raises_400(monkeypatch):
    _patch_supabase(
        monkeypatch,
        FakeGoTrue(error=AuthApiError("Token has expired or is invalid", 403, None)),
    )

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.verify_signup_otp("alice@example.com", "000000")

    assert exc_info.value.status_code == 400


async def test_verify_signup_otp_no_session_raises_400(monkeypatch):
    """Defensive: verify_otp succeeding with no session/user would be an
    unexpected Supabase response shape, not something to silently pass
    through as a login."""
    user = FakeUser(created_at=NOW, last_sign_in_at=NOW, email_confirmed_at=None)
    _patch_supabase(monkeypatch, FakeGoTrue(response=FakeAuthResponse(user, None)))

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.verify_signup_otp("alice@example.com", "123456")

    assert exc_info.value.status_code == 400
