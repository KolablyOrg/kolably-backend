"""
Authentication routes — backend facade over Supabase Auth.

Frontend calls these endpoints only. Supabase is a hidden implementation detail.
"""

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.dependencies import get_current_user
from app.schemas.auth import (
    AuthTokenResponse,
    BusinessSignupRequest,
    CreatorSignupRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshTokenRequest,
    ResetPasswordRequest,
    UpdateProfileRequest,
)
from app.schemas.user import UserInToken
from app.services import auth_service

router = APIRouter()
security = HTTPBearer()


# ── Signup ────────────────────────────────────────────

@router.post("/signup/creator", response_model=AuthTokenResponse)
async def signup_creator(data: CreatorSignupRequest):
    """Register a new creator account."""
    return await auth_service.signup_creator(data)


@router.post("/signup/business", response_model=AuthTokenResponse)
async def signup_business(data: BusinessSignupRequest):
    """Register a new business account."""
    return await auth_service.signup_business(data)


# ── Login / Logout ────────────────────────────────────

@router.post("/login", response_model=AuthTokenResponse)
async def login(data: LoginRequest):
    """Authenticate user and return tokens + profile."""
    return await auth_service.login(data)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Sign out — invalidate the current session."""
    return await auth_service.logout(credentials.credentials)


# ── Token Refresh ─────────────────────────────────────

@router.post("/refresh", response_model=AuthTokenResponse)
async def refresh_token(data: RefreshTokenRequest):
    """Refresh an expired access token."""
    return await auth_service.refresh_session(data.refresh_token)


# ── Password Reset ────────────────────────────────────

@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(data: ForgotPasswordRequest):
    """Send password reset email."""
    return await auth_service.forgot_password(data.email)


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(data: ResetPasswordRequest):
    """Reset user password with valid reset token."""
    return await auth_service.reset_password(data.access_token, data.new_password)


# ── Current User ──────────────────────────────────────

@router.get("/me")
async def get_me(user: UserInToken = Depends(get_current_user)):
    """Get current user's profile + role-specific data."""
    return await auth_service.get_user_profile(user.auth_id)


@router.patch("/me")
async def update_me(
    data: UpdateProfileRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Update current user's profile fields."""
    return await auth_service.update_user_profile(
        profile_id=user.id,
        auth_id=user.auth_id,
        role=user.role,
        data=data,
    )
