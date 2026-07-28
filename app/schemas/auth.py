"""
Auth-related Pydantic schemas — request/response models for all auth endpoints.
"""

from typing import Literal

from pydantic import BaseModel, EmailStr, Field


# ── Signup Requests ───────────────────────────────────
class CreatorSignupRequest(BaseModel):
    name: str
    username: str
    email: EmailStr
    password: str = Field(..., min_length=8)
    city: str
    instagram_handle: str
    niche: str
    follower_count: int = Field(..., ge=0)
    profile_photo_url: str | None = None


class BusinessSignupRequest(BaseModel):
    business_name: str
    owner_name: str
    email: EmailStr
    password: str = Field(..., min_length=8)
    business_category: str
    city: str
    address: str
    business_description: str | None = None


# ── Login ─────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# ── Google Sign-In ────────────────────────────────────
class GoogleAuthRequest(BaseModel):
    """Google Identity Services / native Google Sign-In ID token exchange.

    `role` is only required the first time a given Google account signs in
    (it decides whether a creator or business profile gets created) — it is
    ignored for returning users.
    """

    id_token: str = Field(..., min_length=1)
    role: Literal["creator", "business"] | None = None
    nonce: str | None = None
    """Raw (unhashed) nonce — required only if the frontend's Google
    Identity Services config included a hashed nonce when requesting the
    credential. Must be present/absent on both sides together, or Supabase
    rejects the token with 'Passed nonce and nonce in id_token should
    either both exist or not.'"""


# ── Instagram Sign-In ─────────────────────────────────
class InstagramAuthRequest(BaseModel):
    """Instagram API with Instagram Login — authorization code exchange.

    Creator-only. `role` is only required on first-time sign-up (mirrors
    `GoogleAuthRequest`) — always "creator" since businesses never connect
    Instagram in this product.
    """

    code: str = Field(..., min_length=1)
    redirect_uri: str = Field(..., min_length=1)
    role: Literal["creator"] | None = None


# ── Token Refresh ────────────────────────────────────
class RefreshTokenRequest(BaseModel):
    refresh_token: str


# ── Password Reset ────────────────────────────────────
class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    access_token: str
    new_password: str = Field(..., min_length=8)


# ── Responses ─────────────────────────────────────────
class AuthTokenResponse(BaseModel):
    """Returned on signup, login, and token refresh."""

    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    user: dict | None = None  # profile + role info


class GoogleAuthResponse(AuthTokenResponse):
    """Returned by POST /auth/google — adds whether this was a first-time sign-up."""

    is_new_user: bool = False


class InstagramAuthResponse(AuthTokenResponse):
    """Returned by POST /auth/instagram — adds whether this was a first-time sign-up."""

    is_new_user: bool = False


class MessageResponse(BaseModel):
    """Generic success message."""

    message: str


# ── Profile Update ────────────────────────────────────
class UpdateProfileRequest(BaseModel):
    """Fields that can be updated for either Creator or Business."""

    # Common
    city: str | None = None

    # Creator specific
    name: str | None = None
    username: str | None = None
    instagram_handle: str | None = None
    niche: str | None = None
    follower_count: int | None = Field(None, ge=0)
    profile_photo_url: str | None = None

    # Business specific
    business_name: str | None = None
    owner_name: str | None = None
    business_category: str | None = None
    address: str | None = None
    business_description: str | None = None
