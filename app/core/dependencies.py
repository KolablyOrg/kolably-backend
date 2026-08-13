"""
FastAPI dependency injection helpers — auth & RBAC.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.enums import UserRole
from app.core.security import verify_supabase_token
from app.core.supabase import get_supabase_admin_client
from app.repositories.creator_repo import CreatorRepository
from app.schemas.user import UserInToken

security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserInToken:
    """
    Decode Supabase JWT → load profile from DB → return UserInToken.

    Checks:
    1. JWT is valid and not expired
    2. Profile exists in public.profiles
    3. Account is active

    Note: email verification is enforced at login (Supabase Auth won't issue
    sessions to unverified users when confirmation is enabled). The JWT itself
    does not carry an email_confirmed_at claim.
    """
    token = credentials.credentials

    # 1. Verify Supabase JWT
    payload = verify_supabase_token(token)

    # 2. Load profile from DB
    auth_id = payload.get("sub")
    if not auth_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing subject",
        )

    supabase = await get_supabase_admin_client()
    result = await (
        supabase.table("profiles")
        .select("*")
        .eq("auth_id", auth_id)
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found",
        )

    profile = result.data

    # 3. Check active
    if not profile.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    return UserInToken(
        id=profile["id"],
        auth_id=auth_id,
        email=profile["email"],
        role=UserRole(profile["role"]),
        is_active=profile["is_active"],
    )


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_security),
) -> UserInToken | None:
    """Return the authenticated user when a valid token is present; otherwise None."""
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


def require_role(*allowed_roles: UserRole):
    """
    Factory that returns a dependency checking the user's role.

    Usage:
        @router.get("/")
        async def my_route(user = Depends(require_role(UserRole.BUSINESS, UserRole.SUPERADMIN))):
            ...
    """

    async def _check_role(
        user: UserInToken = Depends(get_current_user),
    ) -> UserInToken:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role.value}' is not allowed. Required: {[r.value for r in allowed_roles]}",
            )
        return user

    return _check_role


async def require_instagram_connected(
    user: UserInToken = Depends(get_current_user),
) -> UserInToken:
    """
    Mandatory onboarding gate: a creator must have Instagram connected before
    using creator-facing actions (applying, submitting content, messaging).

    Only enforced for role=creator — Google/email signups have no Instagram
    data yet and must connect during onboarding; Instagram signups already
    arrive connected (see `auth_service.instagram_auth`). Superadmins bypass
    entirely (they may not even have a `creators` row).
    """
    if user.role == UserRole.CREATOR:
        creator = await CreatorRepository().get_by_profile_id(user.id)
        if not creator or not creator.instagram_access_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Connect your Instagram to do this — brands need verified reach before you can apply, save campaigns, or message them.",
            )
    return user
