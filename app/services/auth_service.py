import logging
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from supabase_auth.errors import AuthApiError

from app.core.config import settings
from app.core.crypto import encrypt_token
from app.core.supabase import get_supabase_admin_client, get_supabase_client
from app.models.user import UserProfile
from app.repositories.business_repo import BusinessRepository
from app.repositories.creator_repo import CreatorRepository
from app.repositories.login_event_repo import LoginEventRepository
from app.repositories.profile_repo import ProfileRepository
from app.schemas.auth import (
    BusinessSignupRequest,
    CreatorSignupRequest,
    GoogleAuthRequest,
    GoogleCodeAuthRequest,
    InstagramAuthRequest,
    LoginRequest,
    UpdateProfileRequest,
)
from app.services import business_access, google_oauth_service, instagram_service, twofa_service

logger = logging.getLogger(__name__)

# GoTrue sets last_sign_in_at == created_at (to the second) only on the very
# first sign-in for an auth.users row; a small tolerance absorbs clock/DB skew.
_NEW_USER_SIGN_IN_TOLERANCE_SECONDS = 5

_ALLOWED_SIGNUP_CONFIRM_REDIRECTS = {
    settings.WEB_SIGNUP_CONFIRM_REDIRECT_URL,
    settings.MOBILE_SIGNUP_CONFIRM_REDIRECT_URL,
}


def _signup_confirm_redirect(redirect_to: str | None) -> str:
    """Only ever forward a redirect_to we recognize — an arbitrary
    client-supplied URL here would otherwise let anyone turn signup into an
    open redirect for the confirmation link. Falls back to the web URL,
    which works whether or not the caller has the mobile app installed.
    Same reasoning as forgot_password's allow-list."""
    return (
        redirect_to
        if redirect_to in _ALLOWED_SIGNUP_CONFIRM_REDIRECTS
        else settings.WEB_SIGNUP_CONFIRM_REDIRECT_URL
    )


async def _record_login_event(profile_id: str, ip_address: str | None, user_agent: str | None) -> None:
    """Best-effort — a logging failure must never block a real login."""
    try:
        await LoginEventRepository().record(profile_id, ip_address, user_agent)
    except Exception:
        logger.exception("Failed to record login event for profile_id=%s", profile_id)


def _profile_to_dict(profile: UserProfile) -> dict:
    """Convert a UserProfile model to a plain dict for JSON responses."""
    return {
        "id": profile.id,
        "auth_id": profile.auth_id,
        "email": profile.email,
        "role": profile.role.value if hasattr(profile.role, "value") else profile.role,
        "full_name": profile.full_name,
        "avatar_url": profile.avatar_url,
        "phone": profile.phone,
        "is_active": profile.is_active,
        "email_confirmed_at": profile.email_confirmed_at,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
        "totp_enabled": profile.totp_enabled,
    }


def _is_repeated_signup(auth_response) -> bool:
    """True when this signup was for an email that's already registered
    and confirmed.

    Supabase deliberately doesn't raise for that case — it returns 200
    with a *sanitized* user: a freshly generated random id, a nulled
    `email_confirmed_at`, and an empty `identities` list (GoTrue's
    sanitizeUser). That's an anti-enumeration measure, so this endpoint
    can't be used to probe which emails have accounts.

    The empty `identities` list is the documented way to tell that fake
    user apart from a genuine new signup, which always comes back with
    exactly one identity. Looking the id up in `profiles` is NOT enough:
    the random id simply won't match anything, which is indistinguishable
    from the signup trigger having failed — that's exactly what happened
    before this check existed, and a duplicate signup 500'd with a
    misleading "Profile creation trigger failed".
    """
    identities = auth_response.user.identities
    return identities is not None and len(identities) == 0


_ACCOUNT_EXISTS_DETAIL = "An account with this email already exists. Try signing in instead."


def _confirmed_session_tokens(auth_response) -> tuple[str | None, str | None]:
    """Only hand back real tokens if the email is actually confirmed.

    `auth_implementation.md` documents "Supabase Auth won't issue a session
    to an unverified user" as the design assumption — but that's a property
    of the Supabase project's own "Confirm email" auth setting, not
    something this code enforces. If that setting is ever off (as it
    currently is), `sign_up()` returns a full session immediately
    regardless of confirmation, and blindly forwarding it would let anyone
    sign up with an email they don't own and land straight in the app with
    zero verification. Withholding the tokens here makes the guarantee true
    independent of that dashboard setting — `login()` already has the
    equivalent check for the sign-in path.
    """
    session = auth_response.session
    if not session or not auth_response.user.email_confirmed_at:
        return None, None
    return session.access_token, session.refresh_token


async def signup_creator(
    data: CreatorSignupRequest,
    *,
    profile_repo: ProfileRepository | None = None,
    creator_repo: CreatorRepository | None = None,
) -> dict:
    supabase = await get_supabase_client()

    try:
        auth_response = await supabase.auth.sign_up(
            {
                "email": data.email,
                "password": data.password,
                "options": {
                    "data": {"role": "creator"},
                    # Only matters if someone clicks the link instead of
                    # using the code — see WEB_SIGNUP_CONFIRM_REDIRECT_URL /
                    # MOBILE_SIGNUP_CONFIRM_REDIRECT_URL.
                    "email_redirect_to": _signup_confirm_redirect(data.redirect_to),
                },
            }
        )
    except AuthApiError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if not auth_response.user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Signup failed — user not created",
        )

    # Must come before the profile lookup below — the sanitized user
    # Supabase returns here carries a random id that matches no profile,
    # which would otherwise fall into the "trigger failed" 500.
    if _is_repeated_signup(auth_response):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_ACCOUNT_EXISTS_DETAIL,
        )

    auth_id = str(auth_response.user.id)

    profile_repo = profile_repo or ProfileRepository()
    profile = await profile_repo.get_by_auth_id(auth_id)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Profile creation trigger failed",
        )

    profile_id = profile.id

    creator_repo = creator_repo or CreatorRepository()
    existing_creator = await creator_repo.get_by_profile_id(profile_id)

    if existing_creator and auth_response.user.email_confirmed_at:
        # sign_up() doesn't error for an email that's already registered —
        # Supabase returns 200 with that account's real id and no session
        # (logged as "user_repeated_signup"), by design, so this endpoint
        # can't be used to enumerate registered emails. Inserting
        # unconditionally below would 500 on creators_profile_id_key's
        # unique constraint instead of giving a real answer.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_ACCOUNT_EXISTS_DETAIL,
        )
    elif not existing_creator:
        await creator_repo.insert_creator({
            "profile_id": profile_id,
            "name": data.name,
            "username": data.username,
            "city": data.city,
            "niche": data.niche,
            "profile_photo_url": data.profile_photo_url,
            # follower_count/instagram_handle intentionally omitted — they
            # stay at their DB defaults (0 / null) until the creator
            # actually connects Instagram via connect_instagram, which is
            # the only legitimate writer of those columns.
        })
    # else: existing_creator is set but the account isn't confirmed yet —
    # someone re-submitting signup before finishing verification. Nothing
    # new to insert; fall through and respond exactly like a first-time
    # signup would (withheld tokens, same profile data), which sends them
    # back to the verify-email screen instead of a scary duplicate error.

    access_token, refresh_token = _confirmed_session_tokens(auth_response)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": profile_id,
            "email": data.email,
            "role": "creator",
            "creator": {
                "name": data.name,
                "username": data.username,
                "city": data.city,
                "niche": data.niche,
            },
        },
    }


async def signup_business(
    data: BusinessSignupRequest,
    *,
    profile_repo: ProfileRepository | None = None,
    business_repo: BusinessRepository | None = None,
) -> dict:
    supabase = await get_supabase_client()

    try:
        auth_response = await supabase.auth.sign_up(
            {
                "email": data.email,
                "password": data.password,
                "options": {
                    "data": {"role": "business"},
                    "email_redirect_to": _signup_confirm_redirect(data.redirect_to),
                },
            }
        )
    except AuthApiError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if not auth_response.user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Signup failed — user not created",
        )

    # See the matching check in signup_creator — must precede the profile
    # lookup, whose 500 this was surfacing as.
    if _is_repeated_signup(auth_response):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_ACCOUNT_EXISTS_DETAIL,
        )

    auth_id = str(auth_response.user.id)

    profile_repo = profile_repo or ProfileRepository()
    profile = await profile_repo.get_by_auth_id(auth_id)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Profile creation trigger failed",
        )

    profile_id = profile.id

    business_repo = business_repo or BusinessRepository()
    existing_business = await business_repo.get_by_profile_id(profile_id)

    if existing_business and auth_response.user.email_confirmed_at:
        # See the matching check in signup_creator — sign_up() returns 200
        # with the existing user's real id and no session for an
        # already-registered email instead of erroring, so this has to be
        # caught explicitly or the insert below 500s on
        # businesses_profile_id_key's unique constraint.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_ACCOUNT_EXISTS_DETAIL,
        )
    elif not existing_business:
        await business_repo.insert_business({
            "profile_id": profile_id,
            "owner_name": data.name,
        })
    # else: existing but unconfirmed — retrying signup before verifying.
    # Fall through to the normal withheld-tokens response.

    access_token, refresh_token = _confirmed_session_tokens(auth_response)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": profile_id,
            "email": data.email,
            "role": "business",
            "business": {
                "owner_name": data.name,
            },
        },
    }


async def login(
    data: LoginRequest,
    *,
    profile_repo: ProfileRepository | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    supabase = await get_supabase_client()

    try:
        auth_response = await supabase.auth.sign_in_with_password(
            {
                "email": data.email,
                "password": data.password,
            }
        )
    except AuthApiError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )

    if not auth_response.user or not auth_response.session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not auth_response.user.email_confirmed_at:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please check your inbox.",
        )

    auth_id = str(auth_response.user.id)
    profile_repo = profile_repo or ProfileRepository()
    profile = await profile_repo.get_by_auth_id(auth_id)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found",
        )

    if not profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    session = auth_response.session
    await _record_login_event(profile.id, ip_address, user_agent)

    if profile.totp_enabled:
        # Withhold real tokens until POST /auth/2fa/verify — see
        # twofa_service module docstring for why this is custom rather than
        # Supabase's built-in MFA.
        mfa_token = twofa_service.mint_mfa_token(
            profile_id=profile.id,
            access_token=session.access_token,
            refresh_token=session.refresh_token,
        )
        return {"mfa_required": True, "mfa_token": mfa_token}

    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "token_type": "bearer",
        "user": {
            "id": profile.id,
            "email": profile.email,
            "role": profile.role.value if hasattr(profile.role, "value") else profile.role,
            "is_active": profile.is_active,
        },
    }


async def google_auth(
    data: GoogleAuthRequest,
    *,
    profile_repo: ProfileRepository | None = None,
    creator_repo: CreatorRepository | None = None,
    business_repo: BusinessRepository | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    """Sign in (or sign up) with a Google ID token obtained by the frontend.

    Supabase verifies the token against Google and creates/reuses the
    auth.users row; our DB trigger auto-creates a matching `profiles` row
    (always with role='creator' — the trigger has no way to know the
    frontend's intended role). For a brand-new sign-in we correct the role
    from `data.role` and create a minimal creator/business row from whatever
    Google gives us (name, avatar) — the frontend is expected to route the
    user to complete their profile afterward via `PATCH /me`.
    """
    supabase = await get_supabase_client()

    credentials = {"provider": "google", "token": data.id_token}
    if data.nonce:
        credentials["nonce"] = data.nonce

    try:
        auth_response = await supabase.auth.sign_in_with_id_token(credentials)
    except AuthApiError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )

    if not auth_response.user or not auth_response.session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google sign-in failed",
        )

    auth_user = auth_response.user
    auth_id = str(auth_user.id)
    is_new_user = auth_user.last_sign_in_at is not None and (
        abs((auth_user.last_sign_in_at - auth_user.created_at).total_seconds())
        < _NEW_USER_SIGN_IN_TOLERANCE_SECONDS
    )

    profile_repo = profile_repo or ProfileRepository()
    profile = await profile_repo.get_by_auth_id(auth_id)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Profile creation trigger failed",
        )

    if not profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    if is_new_user:
        if data.role is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="role ('creator' or 'business') is required for first-time Google sign-in",
            )

        metadata = auth_user.user_metadata or {}
        display_name = metadata.get("full_name") or metadata.get("name") or profile.email.split("@")[0]
        avatar_url = metadata.get("avatar_url") or metadata.get("picture")

        if profile.role != data.role:
            profile = await profile_repo.update_role(profile.id, data.role) or profile

        if data.role == "creator":
            creator_repo = creator_repo or CreatorRepository()
            await creator_repo.insert_creator({
                "profile_id": profile.id,
                "name": display_name,
                "profile_photo_url": avatar_url,
            })
        else:
            business_repo = business_repo or BusinessRepository()
            await business_repo.insert_business({
                "profile_id": profile.id,
                "business_name": display_name,
                "logo_url": avatar_url,
            })

    session = auth_response.session
    await _record_login_event(profile.id, ip_address, user_agent)
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "token_type": "bearer",
        "user": {
            "id": profile.id,
            "email": profile.email,
            "role": profile.role.value if hasattr(profile.role, "value") else profile.role,
            "is_active": profile.is_active,
        },
        "is_new_user": is_new_user,
    }


async def google_code_auth(
    data: GoogleCodeAuthRequest,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    """Code-exchange counterpart to `google_auth` — for clients using the
    backend's OAuth relay (GET /auth/google/login-url + /callback) instead
    of a native Google Sign-In dev-client build. Exchanges the authorization
    `code` for an id_token server-side, then defers to the exact same
    sign-in/sign-up logic as the direct id_token flow."""
    id_token = await google_oauth_service.exchange_code_for_id_token(data.code)
    return await google_auth(
        GoogleAuthRequest(id_token=id_token, role=data.role),
        ip_address=ip_address,
        user_agent=user_agent,
    )


async def _mint_session_for_email(email: str):
    """Mint a real Supabase session for `email` with nothing sent anywhere.

    Instagram gives us no password and isn't a Supabase-recognized ID-token
    provider (unlike Google), so there's no `sign_up`/`sign_in_with_id_token`
    call that fits. Instead: generate a magic-link token server-side via the
    admin API, then immediately verify it server-side — the "link" is never
    emailed, it's just used as a one-time bridge to a real session.
    """
    supabase_admin = await get_supabase_admin_client()
    link = await supabase_admin.auth.admin.generate_link({"type": "magiclink", "email": email})

    supabase_anon = await get_supabase_client()
    auth_response = await supabase_anon.auth.verify_otp({
        "token_hash": link.properties.hashed_token,
        "type": "magiclink",
    })
    return auth_response.session


async def instagram_auth(
    data: InstagramAuthRequest,
    *,
    profile_repo: ProfileRepository | None = None,
    creator_repo: CreatorRepository | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    """Sign in (or sign up) via Instagram API with Instagram Login.

    Creator-only. A brand-new sign-in gets a full one-tap profile pre-fill
    (name/bio/website/photo/follower stats/engagement rate) plus a portfolio
    import — no separate onboarding step needed, unlike Google/email signups
    which still have to connect Instagram afterward. A returning sign-in only
    refreshes the stats subset, matching the connect-once/sync-stats-only
    split already documented for `/creators/me/instagram/sync` in
    `API_REQUIREMENTS.md` §2.

    `data.redirect_uri` is accepted for API compatibility but unused — see
    `creator_service.connect_instagram` for why the token exchange always
    uses the fixed relay URL instead.
    """
    short_lived = await instagram_service.exchange_code_for_token(
        data.code, instagram_service.relay_redirect_uri()
    )
    long_lived = await instagram_service.exchange_for_long_lived_token(short_lived["access_token"])
    access_token = long_lived["access_token"]

    ig_profile = await instagram_service.fetch_profile(access_token)
    instagram_user_id = str(ig_profile["user_id"])

    creator_repo = creator_repo or CreatorRepository()
    profile_repo = profile_repo or ProfileRepository()

    expires_at = datetime.now(UTC) + timedelta(seconds=long_lived.get("expires_in", 5_184_000))
    encrypted_token = encrypt_token(access_token)
    now = datetime.now(UTC).isoformat()

    existing_creator = await creator_repo.get_by_instagram_user_id(instagram_user_id)

    if existing_creator:
        profile = await profile_repo.get_by_id(existing_creator.profile_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Profile not found for existing creator",
            )
        if not profile.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated",
            )

        await creator_repo.update_by_profile_id(existing_creator.profile_id, {
            "follower_count": ig_profile.get("followers_count"),
            "following_count": ig_profile.get("follows_count"),
            "profile_photo_url": ig_profile.get("profile_picture_url"),
            "instagram_access_token": encrypted_token,
            "instagram_token_expires_at": expires_at.isoformat(),
            "instagram_synced_at": now,
        })

        session = await _mint_session_for_email(profile.email)
        await _record_login_event(profile.id, ip_address, user_agent)
        return {
            "access_token": session.access_token,
            "refresh_token": session.refresh_token,
            "token_type": "bearer",
            "user": {
                "id": profile.id,
                "email": profile.email,
                "role": profile.role.value if hasattr(profile.role, "value") else profile.role,
                "is_active": profile.is_active,
            },
            "is_new_user": False,
        }

    # First-time Instagram sign-in — always a new creator account.
    if data.role != "creator":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="role ('creator') is required for first-time Instagram sign-in",
        )

    placeholder_email = f"ig_{instagram_user_id}@users.kolably.instagram"

    supabase_admin = await get_supabase_admin_client()
    try:
        user_response = await supabase_admin.auth.admin.create_user({
            "email": placeholder_email,
            "email_confirm": True,
            "user_metadata": {"role": "creator"},
        })
    except AuthApiError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    auth_id = str(user_response.user.id)
    profile = await profile_repo.get_by_auth_id(auth_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Profile creation trigger failed",
        )

    media = await instagram_service.fetch_media(access_token)
    engagement_rate = await instagram_service.calculate_engagement_rate(access_token, media)

    new_creator = await creator_repo.insert_creator({
        "profile_id": profile.id,
        "username": ig_profile["username"],
        "instagram_handle": ig_profile["username"],
        "instagram_user_id": instagram_user_id,
        "instagram_access_token": encrypted_token,
        "instagram_token_expires_at": expires_at.isoformat(),
        "instagram_synced_at": now,
        **instagram_service.build_profile_prefill(ig_profile, engagement_rate),
    })

    if media and new_creator:
        await creator_repo.insert_portfolio_items(
            instagram_service.build_portfolio_items(new_creator.id, media)
        )

    session = await _mint_session_for_email(placeholder_email)
    await _record_login_event(profile.id, ip_address, user_agent)
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "token_type": "bearer",
        "user": {
            "id": profile.id,
            "email": profile.email,
            "role": profile.role.value if hasattr(profile.role, "value") else profile.role,
            "is_active": profile.is_active,
        },
        "is_new_user": True,
    }


async def refresh_session(refresh_token: str) -> dict:
    supabase = await get_supabase_client()

    try:
        auth_response = await supabase.auth.refresh_session(refresh_token)
    except AuthApiError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )

    if not auth_response.session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to refresh session",
        )

    session = auth_response.session
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "token_type": "bearer",
    }


async def logout(access_token: str) -> dict:
    """Revoke the given access token.

    `supabase.auth.sign_out()` only signs out the *client instance's own*
    loaded session — it takes no token argument, and `get_supabase_client()`
    always returns a fresh, session-less client, so it can never revoke the
    caller's token. `admin.sign_out(jwt, ...)` is the one that actually
    revokes an arbitrary token passed in directly.
    """
    supabase = await get_supabase_admin_client()

    try:
        await supabase.auth.admin.sign_out(access_token, "global")
    except AuthApiError:
        pass

    return {"message": "Logged out successfully"}


_ALLOWED_PASSWORD_RESET_REDIRECTS = {
    settings.WEB_PASSWORD_RESET_REDIRECT_URL,
    settings.MOBILE_PASSWORD_RESET_REDIRECT_URL,
}


async def forgot_password(email: str, redirect_to: str | None = None) -> dict:
    supabase = await get_supabase_client()

    # Only ever forward a redirect_to we recognize — an arbitrary
    # client-supplied URL here would otherwise let anyone turn this endpoint
    # into an open redirect for the recovery link. Falls back to the web
    # URL since that works whether or not the caller has the mobile app.
    target = (
        redirect_to
        if redirect_to in _ALLOWED_PASSWORD_RESET_REDIRECTS
        else settings.WEB_PASSWORD_RESET_REDIRECT_URL
    )

    try:
        await supabase.auth.reset_password_email(email, {"redirect_to": target})
    except AuthApiError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return {"message": "Password reset link sent to your email"}


async def resend_verification_email(email: str, redirect_to: str | None = None) -> dict:
    """Re-sends the signup confirmation email — for the account created but
    never confirmed case (see signup_creator/signup_business: a `session` of
    `None` means Supabase is waiting on this exact email to be confirmed
    before login will work). Same non-leaking shape as forgot_password: a
    generic success message either way, so this can't be used to probe
    which emails have an account.
    """
    supabase = await get_supabase_client()

    try:
        await supabase.auth.resend({
            "type": "signup",
            "email": email,
            "options": {"email_redirect_to": _signup_confirm_redirect(redirect_to)},
        })
    except AuthApiError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return {"message": "Confirmation email sent"}


async def verify_reset_otp(email: str, token: str) -> dict:
    """Confirm a password-reset request with the 6-digit code emailed at
    forgot-password time — the OTP counterpart to clicking the recovery
    link, same reasoning as verify_signup_otp (works identically regardless
    of platform). Deliberately doesn't attach a user profile the way
    verify_signup_otp does: this step doesn't log the person into the app,
    it only hands back an access_token for one immediate follow-up call to
    reset_password — mirroring the link-click path, which has never logged
    anyone in either (see ResetPassword.tsx / reset-password.tsx).
    """
    supabase = await get_supabase_client()

    try:
        auth_response = await supabase.auth.verify_otp({
            "email": email,
            "token": token,
            "type": "recovery",
        })
    except AuthApiError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if not auth_response.session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired code",
        )

    session = auth_response.session
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "token_type": "bearer",
    }


async def verify_signup_otp(
    email: str,
    token: str,
    *,
    profile_repo: ProfileRepository | None = None,
    creator_repo: CreatorRepository | None = None,
    business_repo: BusinessRepository | None = None,
) -> dict:
    """Confirm a signup with the 6-digit code emailed at signup time — the
    OTP counterpart to clicking the confirmation link.

    Chosen over the link for this product specifically because it works
    identically no matter which platform (mobile app vs web app) the person
    is using right now: a link needs a `redirect_to` picked in advance for
    each platform (see the mobile-deep-link vs web-URL split already built
    for password reset), whereas a code just gets typed into whichever app
    the person is already sitting in — nothing to redirect, nothing to get
    wrong per platform.
    """
    supabase = await get_supabase_client()

    try:
        auth_response = await supabase.auth.verify_otp({
            "email": email,
            "token": token,
            "type": "signup",
        })
    except AuthApiError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if not auth_response.user or not auth_response.session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired code",
        )

    auth_id = str(auth_response.user.id)
    # Reuse get_user_profile's already-correct enrichment (creator/business
    # nested data, full_name fallback) instead of hand-rolling a thinner
    # user dict here — a minimal shape would have regressed the blank-name
    # bug that fallback was built to fix.
    user = await get_user_profile(
        auth_id,
        profile_repo=profile_repo,
        creator_repo=creator_repo,
        business_repo=business_repo,
    )

    session = auth_response.session
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "token_type": "bearer",
        "user": user,
    }


async def reset_password(access_token: str, new_password: str) -> dict:
    supabase = await get_supabase_client()

    try:
        await supabase.auth.set_session(access_token, "")
        await supabase.auth.update_user({"password": new_password})
    except AuthApiError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return {"message": "Password updated successfully"}


async def get_user_profile(
    auth_id: str,
    *,
    profile_repo: ProfileRepository | None = None,
    creator_repo: CreatorRepository | None = None,
    business_repo: BusinessRepository | None = None,
) -> dict:
    profile_repo = profile_repo or ProfileRepository()
    profile = await profile_repo.get_by_auth_id(auth_id)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )

    response = _profile_to_dict(profile)

    # profiles.full_name is never written by handle_new_auth_user() (the
    # signup trigger only sets auth_id/email/role), so it's always NULL —
    # fall back to the role-specific record every client actually reads.
    if profile.role.value in ("creator", "superadmin"):
        creator_repo = creator_repo or CreatorRepository()
        creator = await creator_repo.get_by_profile_id(profile.id)
        if creator:
            response["creator"] = creator.to_public_row()
            if not response["full_name"]:
                response["full_name"] = creator.name

    if profile.role.value in ("business", "superadmin"):
        business_repo = business_repo or BusinessRepository()
        # Team members (business_members, not businesses.profile_id) have no
        # row of their own in `businesses` — resolve via business_access so
        # their dashboard (sidebar business name, KYB status, etc.) isn't
        # blank. `team_role` lets the frontend gate owner-only UI without an
        # extra round trip.
        business = await business_access.get_business_for_profile(profile.id, business_repo=business_repo)
        if business:
            response["business"] = business.to_row()
            response["team_role"] = await business_access.get_role_for_profile(
                business.id, profile.id, business_repo=business_repo
            )
            # Only fall back to the business's own name fields when this
            # profile IS that business (the literal owner) — for a team
            # member, `business` belongs to someone else, and owner_name
            # would otherwise show as *their* display name.
            if not response["full_name"] and business.profile_id == profile.id:
                response["full_name"] = business.owner_name or business.business_name

    return response


async def update_user_profile(
    profile_id: str,
    auth_id: str,
    role: str,
    data: UpdateProfileRequest,
    *,
    creator_repo: CreatorRepository | None = None,
    business_repo: BusinessRepository | None = None,
) -> dict:
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        return await get_user_profile(auth_id)

    if role == "creator":
        repo = creator_repo or CreatorRepository()
        # instagram_handle/follower_count deliberately excluded — Instagram
        # data is never self-reportable, see UpdateProfileRequest docstring.
        valid_fields = {
            "name",
            "username",
            "city",
            "tiktok_handle",
            "youtube_handle",
            "niche",
            "profile_photo_url",
            "bio",
            "categories",
            "rate_per_reel",
            "rate_per_story",
            "show_rate_card",
            "open_to",
        }
    elif role == "business":
        repo = business_repo or BusinessRepository()
        valid_fields = {
            "business_name",
            "owner_name",
            "business_category",
            "city",
            "address",
            "business_description",
            "logo_url",
            "website",
        }
    elif role == "superadmin":
        return await get_user_profile(auth_id)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Updates for role '{role}' not supported yet",
        )

    final_update = {}
    for k, v in update_data.items():
        if k in valid_fields:
            if k == "business_category":
                final_update["category"] = v
            elif k == "business_description":
                final_update["description"] = v
            else:
                final_update[k] = v

    if role == "creator" and "categories" in final_update:
        cats = final_update["categories"]
        if isinstance(cats, list) and len(cats) > 0:
            final_update["niche"] = cats[0]

    if not final_update:
        return await get_user_profile(auth_id)

    result = await repo.update_by_profile_id(profile_id, final_update)

    if not result:
        table_name = "creators" if role == "creator" else "businesses"
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Could not find {table_name} record to update",
        )

    return await get_user_profile(auth_id)


async def list_login_events(profile_id: str, *, repo: LoginEventRepository | None = None) -> list[dict]:
    repo = repo or LoginEventRepository()
    return await repo.list_recent(profile_id)


async def revoke_other_sessions(access_token: str) -> dict:
    """Sign the current device out of every OTHER session — Supabase's admin
    API has no per-device revoke, only global/local/others scopes (see
    `logout`'s docstring for why `admin.sign_out` needs the raw token)."""
    supabase = await get_supabase_admin_client()
    try:
        await supabase.auth.admin.sign_out(access_token, "others")
    except AuthApiError:
        pass
    return {"message": "Signed out of all other sessions"}


async def delete_user_account(
    profile_id: str,
    *,
    profile_repo: ProfileRepository | None = None,
) -> dict:
    """Deactivate user account and set is_active = False."""
    profile_repo = profile_repo or ProfileRepository()
    updated = await profile_repo.update(profile_id, {"is_active": False})
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found",
        )
    return {"message": "Account deactivated successfully"}
