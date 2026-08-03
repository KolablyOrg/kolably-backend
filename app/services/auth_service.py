from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from supabase_auth.errors import AuthApiError

from app.core.config import settings
from app.core.crypto import encrypt_token
from app.core.supabase import get_supabase_admin_client, get_supabase_client
from app.models.user import UserProfile
from app.repositories.business_repo import BusinessRepository
from app.repositories.creator_repo import CreatorRepository
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
from app.services import google_oauth_service, instagram_service

# GoTrue sets last_sign_in_at == created_at (to the second) only on the very
# first sign-in for an auth.users row; a small tolerance absorbs clock/DB skew.
_NEW_USER_SIGN_IN_TOLERANCE_SECONDS = 5


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
    }


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
    await creator_repo.insert_creator({
        "profile_id": profile_id,
        "name": data.name,
        "username": data.username,
        "city": data.city,
        "niche": data.niche,
        "follower_count": data.follower_count,
        "instagram_handle": data.instagram_handle,
        "profile_photo_url": data.profile_photo_url,
    })

    session = auth_response.session
    return {
        "access_token": session.access_token if session else None,
        "refresh_token": session.refresh_token if session else None,
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
    await business_repo.insert_business({
        "profile_id": profile_id,
        "business_name": data.business_name,
        "owner_name": data.owner_name,
        "category": data.business_category,
        "city": data.city,
        "address": data.address,
        "description": data.business_description,
    })

    session = auth_response.session
    return {
        "access_token": session.access_token if session else None,
        "refresh_token": session.refresh_token if session else None,
        "token_type": "bearer",
        "user": {
            "id": profile_id,
            "email": data.email,
            "role": "business",
            "business": {
                "business_name": data.business_name,
                "owner_name": data.owner_name,
                "city": data.city,
                "category": data.business_category,
            },
        },
    }


async def login(
    data: LoginRequest,
    *,
    profile_repo: ProfileRepository | None = None,
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


async def google_code_auth(data: GoogleCodeAuthRequest) -> dict:
    """Code-exchange counterpart to `google_auth` — for clients using the
    backend's OAuth relay (GET /auth/google/login-url + /callback) instead
    of a native Google Sign-In dev-client build. Exchanges the authorization
    `code` for an id_token server-side, then defers to the exact same
    sign-in/sign-up logic as the direct id_token flow."""
    id_token = await google_oauth_service.exchange_code_for_id_token(data.code)
    return await google_auth(GoogleAuthRequest(id_token=id_token, role=data.role))


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
        business = await business_repo.get_by_profile_id(profile.id)
        if business:
            response["business"] = business.to_row()
            if not response["full_name"]:
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
        valid_fields = {
            "name",
            "username",
            "city",
            "instagram_handle",
            "niche",
            "follower_count",
            "profile_photo_url",
            "bio",
            "categories",
            "rate_per_reel",
            "rate_per_story",
            "show_rate_card",
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
