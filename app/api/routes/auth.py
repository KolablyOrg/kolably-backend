"""
Authentication routes — backend facade over Supabase Auth.

Frontend calls these endpoints only. Supabase is a hidden implementation detail.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.dependencies import get_current_user
from app.schemas.auth import (
    AuthTokenResponse,
    BusinessSignupRequest,
    CreatorSignupRequest,
    ForgotPasswordRequest,
    GoogleAuthRequest,
    GoogleAuthResponse,
    GoogleCodeAuthRequest,
    InstagramAuthRequest,
    InstagramAuthResponse,
    LoginEventResponse,
    LoginRequest,
    MessageResponse,
    RefreshTokenRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TwoFactorCodeRequest,
    TwoFactorSetupResponse,
    TwoFactorStatusResponse,
    TwoFactorVerifyLoginRequest,
    UpdateProfileRequest,
    VerifySignupOtpRequest,
)
from app.schemas.user import UserInToken
from app.services import auth_service, google_oauth_service, instagram_service, twofa_service

router = APIRouter()
security = HTTPBearer()
logger = logging.getLogger(__name__)


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
async def login(data: LoginRequest, request: Request):
    """Authenticate user and return tokens + profile — or, if 2FA is
    enabled, an `mfa_token` that POST /auth/2fa/verify exchanges for tokens."""
    return await auth_service.login(
        data, ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/google", response_model=GoogleAuthResponse)
async def google_auth(data: GoogleAuthRequest, request: Request):
    """Sign in or sign up with a Google ID token.

    `role` is required on first sign-in; the frontend should route
    `is_new_user` responses to a profile-completion step (`PATCH /me`).
    """
    return await auth_service.google_auth(
        data, ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.get("/google/login-url")
async def get_google_login_url(
    redirect_uri: str = Query(..., description="Where the client wants the flow to end up (its own app-scheme URI)"),
):
    """Public — no session exists yet. Google's Web-application OAuth client
    only accepts https redirect_uris, so this returns an authorize URL that
    relays back to the client's real `redirect_uri` via `/auth/google/callback`
    (same relay pattern as `/auth/instagram/login-url`)."""
    try:
        return {"url": google_oauth_service.build_authorize_url_with_relay(redirect_uri)}
    except RuntimeError as exc:
        # Common local-dev miss: TOKEN_ENCRYPTION_KEY unset → encrypt_token fails.
        logger.exception("Failed to build Google OAuth authorize URL")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is temporarily unavailable. Please try again shortly.",
        ) from exc


@router.get("/google/callback")
async def google_oauth_callback(
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
):
    """The single fixed HTTPS redirect_uri every relayed Google OAuth flow
    gives to Google. Google redirects here; this relays the result on to
    whatever URI the client packed into `state` when it started the flow."""
    app_redirect_uri = google_oauth_service.decode_app_redirect(state) if state else None
    if not app_redirect_uri:
        return {"detail": "Invalid or expired Google authentication request."}

    separator = "&" if "?" in app_redirect_uri else "?"
    if code:
        return RedirectResponse(url=f"{app_redirect_uri}{separator}code={code}")
    return RedirectResponse(url=f"{app_redirect_uri}{separator}error={error or 'access_denied'}")


@router.post("/google/code", response_model=GoogleAuthResponse)
async def google_code_auth(data: GoogleCodeAuthRequest, request: Request):
    """Sign in or sign up with a Google authorization `code` obtained via the
    relay flow above — the code-exchange counterpart to `POST /auth/google`'s
    direct id_token flow, for clients without a native Google Sign-In
    dev-client build."""
    return await auth_service.google_code_auth(
        data, ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/instagram", response_model=InstagramAuthResponse)
async def instagram_auth(data: InstagramAuthRequest, request: Request):
    """Sign in or sign up via Instagram API with Instagram Login (creators only).

    `role` ("creator") is required on first sign-in. A first-time sign-in
    pre-fills the full profile + portfolio from Instagram — no separate
    "connect Instagram" onboarding step needed, unlike Google/email signups.
    """
    return await auth_service.instagram_auth(
        data, ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.get("/instagram/login-url")
async def get_instagram_login_url(
    redirect_uri: str = Query(..., description="Where the client wants the flow to end up (its own app-scheme URI)"),
):
    """Public — no session exists yet. Instagram only accepts a fixed HTTPS
    redirect_uri (see `instagram_service.relay_redirect_uri`), so this
    returns an authorize URL that relays back to the client's real
    `redirect_uri` via `/auth/instagram/callback`."""
    try:
        return {"url": instagram_service.build_authorize_url_with_relay(redirect_uri)}
    except RuntimeError as exc:
        # Common local-dev miss: TOKEN_ENCRYPTION_KEY unset → encrypt_token fails.
        logger.exception("Failed to build Instagram OAuth authorize URL")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is temporarily unavailable. Please try again shortly.",
        ) from exc


@router.get("/instagram/callback")
async def instagram_oauth_callback(
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
):
    """The single fixed HTTPS redirect_uri every Instagram OAuth flow (both
    login/signup and the creator-connect flow) actually gives to Instagram.
    Instagram redirects here; this relays the result on to whatever URI the
    client packed into `state` when it started the flow."""
    app_redirect_uri = instagram_service.decode_app_redirect(state) if state else None
    if not app_redirect_uri:
        return {"detail": "Invalid or expired Instagram authentication request."}

    separator = "&" if "?" in app_redirect_uri else "?"
    if code:
        return RedirectResponse(url=f"{app_redirect_uri}{separator}code={code}")
    return RedirectResponse(url=f"{app_redirect_uri}{separator}error={error or 'access_denied'}")


@router.post("/logout", response_model=MessageResponse)
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Sign out — invalidate the current session."""
    return await auth_service.logout(credentials.credentials)


@router.get("/sessions", response_model=list[LoginEventResponse])
async def list_sessions(user: UserInToken = Depends(get_current_user)):
    """Recent login history — display-only, see auth_service.list_login_events."""
    return await auth_service.list_login_events(profile_id=user.id)


@router.post("/sessions/revoke-others", response_model=MessageResponse)
async def revoke_other_sessions(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user: UserInToken = Depends(get_current_user),
):
    """Sign out of every other session (not this one) — see
    auth_service.revoke_other_sessions for why this can't be per-device."""
    return await auth_service.revoke_other_sessions(credentials.credentials)


# ── Token Refresh ─────────────────────────────────────

@router.post("/refresh", response_model=AuthTokenResponse)
async def refresh_token(data: RefreshTokenRequest):
    """Refresh an expired access token."""
    return await auth_service.refresh_session(data.refresh_token)


# ── Password Reset ────────────────────────────────────

@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(data: ForgotPasswordRequest):
    """Send password reset email."""
    return await auth_service.forgot_password(data.email, redirect_to=data.redirect_to)


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(data: ResetPasswordRequest):
    """Reset user password with valid reset token."""
    return await auth_service.reset_password(data.access_token, data.new_password)


@router.post("/2fa/setup", response_model=TwoFactorSetupResponse)
async def setup_2fa(user: UserInToken = Depends(get_current_user)):
    """Generate a new TOTP secret (not yet enabled) — the client renders
    `otpauth_url` as a QR code / shows `secret` for manual entry, then
    confirms with POST /auth/2fa/enable."""
    return await twofa_service.setup(profile_id=user.id, email=user.email)


@router.post("/2fa/enable", response_model=TwoFactorStatusResponse)
async def enable_2fa(
    data: TwoFactorCodeRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Confirm the secret from /2fa/setup with a live code and turn 2FA on."""
    return await twofa_service.enable(profile_id=user.id, code=data.code)


@router.post("/2fa/disable", response_model=TwoFactorStatusResponse)
async def disable_2fa(
    data: TwoFactorCodeRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Turn 2FA off — requires a current code, not just being logged in."""
    return await twofa_service.disable(profile_id=user.id, code=data.code)


@router.post("/2fa/verify", response_model=AuthTokenResponse)
async def verify_2fa_login(data: TwoFactorVerifyLoginRequest):
    """Second half of a 2FA-gated login — exchanges the `mfa_token` from
    POST /auth/login (when the account has 2FA enabled) plus a live code for
    real tokens."""
    return await twofa_service.verify_login_mfa(data.mfa_token, data.code)


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(data: ResendVerificationRequest):
    """Re-send the signup confirmation email — for the 'check your email'
    screen a creator/business lands on right after signup."""
    return await auth_service.resend_verification_email(data.email, data.redirect_to)


@router.post("/verify-signup-otp", response_model=AuthTokenResponse)
async def verify_signup_otp(data: VerifySignupOtpRequest):
    """Confirm a signup with the 6-digit code emailed at signup time — the
    OTP counterpart to clicking the confirmation link (see
    auth_service.verify_signup_otp for why OTP was chosen over a link)."""
    return await auth_service.verify_signup_otp(data.email, data.token)


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


@router.delete("/me", response_model=MessageResponse)
async def delete_me(
    user: UserInToken = Depends(get_current_user),
):
    """Deactivate / delete current user's account."""
    return await auth_service.delete_user_account(profile_id=user.id)
