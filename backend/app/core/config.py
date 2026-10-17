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

    # Browser origins allowed to call the API directly (comma-separated), e.g. the teacher panel.
    # The panel talks to the API from its server (BFF), so normally only uploads need this.
    cors_allowed_origins: str = ""
    # Proxies whose X-Forwarded-For header is trusted (comma-separated IPs), e.g. the panel server.
    # From anyone else the header is ignored, so clients cannot fake their IP.
    trusted_proxy_ips: str = ""

    # --- Video (VdoCipher). Empty secret -> MockVideoProvider is used (dev and tests) ---
    vdocipher_api_secret: str = ""
    vdocipher_api_base_url: str = "https://dev.vdocipher.com/api"
    # Shared secret that must be present in the webhook URL (?token=...)
    vdocipher_webhook_secret: str = ""
    # Life of a playback OTP. Hard upper bound: 5 minutes.
    playback_otp_ttl_seconds: int = Field(default=300, ge=30, le=300)
    playback_rate_limit_attempts: int = 10
    playback_rate_limit_window_seconds: int = 60
    # Mock mode only: where browsers upload files (e.g. http://localhost:8000/dev/mock-video-upload).
    # Empty = uploads are impossible and "sync-status" marks videos ready right away.
    mock_video_upload_url: str = ""
    # Mock mode only: how long a video "encodes" before it turns ready (0 = immediately)
    mock_video_processing_seconds: float = 0

    # --- Live lessons: LiveKit. Any of the three empty -> MockLiveProvider (dev and tests) ---
    # URL the mobile app / browser connects to (ws:// locally, wss:// in production)
    livekit_url: str = ""
    # URL the backend uses for server API calls; defaults to livekit_url with http(s)://
    livekit_api_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    live_student_token_ttl_minutes: int = Field(default=10, ge=1, le=30)
    live_teacher_token_ttl_minutes: int = Field(default=60, ge=1, le=240)
    # How long LiveKit keeps an empty room (e.g. teacher's internet dropped) before closing it
    live_room_empty_timeout_seconds: int = Field(default=600, ge=60)
    live_join_rate_limit_attempts: int = 10
    live_join_rate_limit_window_seconds: int = 60

    # --- Temporary storage for raw recordings (S3 / MinIO). Empty -> in-memory mock storage ---
    # Endpoint the BACKEND uses (presigned URLs, deleting files). Empty = real AWS S3.
    recordings_s3_endpoint_url: str = ""
    # Endpoint the EGRESS container uses to upload; locally "http://minio:9000"
    recordings_s3_egress_endpoint_url: str = ""
    recordings_s3_bucket: str = ""
    recordings_s3_region: str = "us-east-1"
    recordings_s3_access_key: str = ""
    recordings_s3_secret_key: str = ""
    # VdoCipher downloads the mp4 through this link; keep it short
    recordings_presigned_url_ttl_seconds: int = Field(default=1800, ge=60, le=6 * 3600)

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def trusted_proxies(self) -> set[str]:
        return {ip.strip() for ip in self.trusted_proxy_ips.split(",") if ip.strip()}

    @property
    def livekit_configured(self) -> bool:
        return bool(self.livekit_url and self.livekit_api_key and self.livekit_api_secret)

    @property
    def recordings_storage_configured(self) -> bool:
        return bool(self.recordings_s3_bucket and self.recordings_s3_access_key and self.recordings_s3_secret_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
