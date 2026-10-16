import logging
from functools import lru_cache

from app.core.config import get_settings
from app.services.live.base import LiveProvider, LiveProviderError, S3Target, build_access_token
from app.services.live.livekit import LiveKitProvider
from app.services.live.mock import MockLiveProvider

logger = logging.getLogger(__name__)

__all__ = [
    "LiveKitProvider",
    "LiveProvider",
    "LiveProviderError",
    "MockLiveProvider",
    "S3Target",
    "build_access_token",
    "get_live_provider",
]


@lru_cache
def get_live_provider() -> LiveProvider:
    """LiveKit when LIVEKIT_URL/API_KEY/API_SECRET are set, otherwise the in-memory mock.

    Used as a FastAPI dependency, so tests can swap it via app.dependency_overrides.
    """
    settings = get_settings()
    if settings.livekit_configured:
        return LiveKitProvider(
            url=settings.livekit_url,
            api_url=settings.livekit_api_url,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
        )
    if settings.environment == "production":
        raise RuntimeError("LiveKit is not configured: refusing to run live lessons on the mock in production")
    logger.warning("LIVEKIT_* settings are empty -> MockLiveProvider is used (no real live video, dev only)")
    return MockLiveProvider()
