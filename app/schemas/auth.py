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
    name: str  # owner's full name
    email: EmailStr
    password: str = Field(..., min_length=8)


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


class GoogleCodeAuthRequest(BaseModel):
    """Authorization-code counterpart to `GoogleAuthRequest`, for clients
    that can't obtain an `id_token` directly (no native Google Sign-In
    dev-client build — see GET /auth/google/login-url + google_oauth_service.py).
    The backend exchanges `code` for an id_token itself, then follows the
    exact same sign-in/sign-up logic as the direct id_token flow.
    """

    code: str = Field(..., min_length=1)
    role: Literal["creator", "business"] | None = None


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
    # Which client the recovery link should return to — validated against a
    # fixed allow-list in auth_service.forgot_password. Optional so existing
    # callers that don't send it still get a safe default.
    redirect_to: str | None = None


class ResendVerificationRequest(BaseModel):
    """POST /auth/resend-verification — re-sends the signup confirmation
    email for an account stuck in the unconfirmed state."""

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
    tiktok_handle: str | None = None
    youtube_handle: str | None = None
    niche: str | None = None
    follower_count: int | None = Field(None, ge=0)
    profile_photo_url: str | None = None
    bio: str | None = None
    categories: list[str] | None = None
    rate_per_reel: int | None = Field(None, ge=0)
    rate_per_story: int | None = Field(None, ge=0)
    show_rate_card: bool | None = None
    open_to: list[str] | None = None

    # Business specific
    business_name: str | None = None
    owner_name: str | None = None
    business_category: str | None = None
    address: str | None = None
    business_description: str | None = None
    logo_url: str | None = None
    website: str | None = None
