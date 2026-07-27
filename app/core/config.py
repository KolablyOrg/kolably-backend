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
