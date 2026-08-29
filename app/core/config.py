"""
Application settings loaded from environment / .env file.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Supabase ──────────────────────────────────────
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""  # anon/public key
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_JWT_SECRET: str = ""  # Settings → API → JWT Secret

    # ── App ───────────────────────────────────────────
    APP_ENV: str = "development"
    DEBUG: bool = True
    # This backend's own public HTTPS origin — Instagram's OAuth product
    # rejects any redirect_uri that isn't https://, so mobile clients can't
    # register their own exp://.../mobile://... scheme with Meta directly.
    # Instead every Instagram OAuth flow redirects here, and this backend
    # relays the result on to whatever URI the client actually wants
    # (see app/api/routes/auth.py:instagram_oauth_callback).
    PUBLIC_API_BASE_URL: str = "https://api.kolably.com"
    # Password-reset email redirect targets. Supabase falls back to the
    # project's dashboard "Site URL" when redirect_to isn't passed
    # explicitly — a stale localhost value here sent every recovery link to
    # a dead page no matter which client requested it. The web and mobile
    # clients each ask for their own via forgot_password's redirect_to
    # param (see auth_service.forgot_password); this is also the fallback
    # for a missing/unrecognized value. Both URLs must be added to
    # Supabase's Redirect URLs allow list (Authentication → URL
    # Configuration) or GoTrue rejects them outright.
    WEB_PASSWORD_RESET_REDIRECT_URL: str = "https://kolably.com/auth/reset-password"
    # Points at the web app's mobile-redirect bridge page, not a raw
    # mobile:// URL — a server-issued redirect (from Supabase's own
    # /auth/v1/verify) straight to a custom scheme unreliably drops the
    # #access_token fragment during the OS app-handoff (confirmed in the
    # wild: one user got a blank page, another had the app open with no
    # token to enter). A normal https redirect never has that problem, so
    # GoTrue lands here first; MobileRedirect.tsx reads the fragment with
    # plain browser JS (100% reliable) and re-launches into the app with the
    # tokens as query params instead, which survive the handoff and which
    # reset-password.tsx / verify-email.tsx already check before the hash.
    MOBILE_PASSWORD_RESET_REDIRECT_URL: str = "https://kolably.com/auth/mobile-redirect"
    # Team-invite emails (POST /businesses/me/team/invite) land here to set a
    # password — must also be added to Supabase's Redirect URLs allow list,
    # same requirement as the password-reset URLs above.
    WEB_TEAM_INVITE_REDIRECT_URL: str = "https://kolably.com/auth/accept-invite"
    # Signup-confirmation emails are OTP-first (see verify_signup_otp) — the
    # code is what the app actually uses. This redirect only matters for
    # someone who clicks the link in the email instead of typing the code:
    # without it, Supabase fell back to the dashboard's default Site URL,
    # which happened to be the password-reset page, so a signup confirmation
    # link was landing people on "Reset your password". Both web and mobile
    # clients ask for their own via signup_creator/signup_business's
    # redirect_to param (same split as password reset above) — a mobile
    # signup whose link opened a browser instead of the app, with no way
    # back except stumbling onto "forgot password", was exactly the bug this
    # split fixes. VerifyEmail.tsx (web) / verify-email.tsx (mobile) both
    # read the access_token appended here and log the person in directly.
    # Both URLs must be added to Supabase's Redirect URLs allow list, same
    # requirement as the URLs above.
    WEB_SIGNUP_CONFIRM_REDIRECT_URL: str = "https://kolably.com/auth/verify-email"
    # Same mobile-redirect bridge page as MOBILE_PASSWORD_RESET_REDIRECT_URL,
    # and for the same reason — see the comment there. MobileRedirect.tsx
    # branches on the `type` GoTrue includes in the fragment (signup vs
    # recovery) to send the app-relaunch to the right screen.
    MOBILE_SIGNUP_CONFIRM_REDIRECT_URL: str = "https://kolably.com/auth/mobile-redirect"
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
        "http://localhost:4173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
        "https://kolably.com",
        "https://www.kolably.com",
    ]

    # ── External Services ─────────────────────────────
    GOOGLE_MAPS_API_KEY: str = ""
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""

    # ── Google OAuth (code-exchange relay for mobile clients without a
    # native Google Sign-In dev-client build — see
    # app/services/google_oauth_service.py). This is the existing "Web
    # application" client (same GOOGLE_CLIENT_ID the web app's Google
    # Identity Services flow already uses) — its client secret is only
    # needed server-side for this authorization-code exchange.
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # ── Instagram (Instagram API with Instagram Login) ─
    INSTAGRAM_APP_ID: str = ""
    INSTAGRAM_APP_SECRET: str = ""

    # ── Meta parent app (Facebook Login for Business product — unused for
    # OAuth, but the Data Deletion Callback is a whole-app setting that may
    # be signed with this secret rather than INSTAGRAM_APP_SECRET) ────────
    APP_SECRET: str = ""

    # ── Token encryption ──────────────────────────────
    TOKEN_ENCRYPTION_KEY: str = ""  # Fernet key — encrypts instagram_access_token at rest

    # ── Bot protection (Cloudflare Turnstile) ──────────
    # Inert until set — no key, no verification call, signups behave exactly
    # as before (see app/core/turnstile.py). Once set, EVERY call to
    # /auth/signup/* must include a valid turnstile_token, including from the
    # mobile app — mobile does not currently obtain one, so setting this
    # will break mobile signup until it integrates Turnstile's mobile SDK too.
    TURNSTILE_SECRET_KEY: str = ""

    # ── S3-Compatible Object Storage (Supabase S3) ───────
    # Used by storage_service for presigned upload/download URLs
    AWS_REGION: str = "ap-south-1"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_BUCKET: str = "media"
    AWS_S3_ENDPOINT_URL: str = "https://uxngcuyrdmajydkqpiyi.storage.supabase.co/storage/v1/s3"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
