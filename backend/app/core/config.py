from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All settings come from environment variables / the `.env` file.

    Required values (no defaults) make the app fail fast if `.env` is missing,
    so a secret can never silently fall back to something hard-coded.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    test_database_url: str | None = None

    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    max_student_devices: int = 2
    device_binding_token_expire_minutes: int = 5

    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 60

    consent_version: str = "1.0"

    # "production" refuses to start with the mock video provider (no DRM there!)
    environment: str = "development"

    # --- Video (VdoCipher). Empty secret -> MockVideoProvider is used (dev and tests) ---
    vdocipher_api_secret: str = ""
    vdocipher_api_base_url: str = "https://dev.vdocipher.com/api"
    # Shared secret that must be present in the webhook URL (?token=...)
    vdocipher_webhook_secret: str = ""
    # Life of a playback OTP. Hard upper bound: 5 minutes.
    playback_otp_ttl_seconds: int = Field(default=300, ge=30, le=300)
    playback_rate_limit_attempts: int = 10
    playback_rate_limit_window_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
