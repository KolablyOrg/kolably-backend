"""
FastAPI dependency injection helpers — auth & RBAC.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.enums import UserRole
from app.core.security import verify_supabase_token
from app.core.supabase import get_supabase_admin_client
from app.schemas.user import UserInToken

security = HTTPBearer()


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

    supabase = get_supabase_admin_client()
    result = (
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
