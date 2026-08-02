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
    # Deep link the password-reset email sends users to. Supabase falls back
    # to the project's dashboard "Site URL" when redirect_to isn't passed
    # explicitly — for this mobile-only app that's a stale localhost value,
    # so every recovery link opened on a phone died on "can't connect".
    # This scheme must also be added to Supabase's Redirect URLs allow list
    # (Authentication → URL Configuration) or GoTrue rejects it outright.
    PASSWORD_RESET_REDIRECT_URL: str = "mobile://reset-password"
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

    # ── Instagram (Instagram API with Instagram Login) ─
    INSTAGRAM_APP_ID: str = ""
    INSTAGRAM_APP_SECRET: str = ""

    # ── Meta parent app (Facebook Login for Business product — unused for
    # OAuth, but the Data Deletion Callback is a whole-app setting that may
    # be signed with this secret rather than INSTAGRAM_APP_SECRET) ────────
    APP_SECRET: str = ""

    # ── Token encryption ──────────────────────────────
    TOKEN_ENCRYPTION_KEY: str = ""  # Fernet key — encrypts instagram_access_token at rest

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
