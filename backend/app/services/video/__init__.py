import logging
from functools import lru_cache

from app.core.config import get_settings
from app.services.video.base import (
    PlaybackCredentials,
    UploadCredentials,
    VideoInfo,
    VideoProvider,
    VideoProviderError,
    Watermark,
)
from app.services.video.mock import MockVideoProvider
from app.services.video.vdocipher import VdoCipherProvider

logger = logging.getLogger(__name__)

__all__ = [
    "MockVideoProvider",
    "PlaybackCredentials",
    "UploadCredentials",
    "VdoCipherProvider",
    "VideoInfo",
    "VideoProvider",
    "VideoProviderError",
    "Watermark",
    "get_video_provider",
]


@lru_cache
def get_video_provider() -> VideoProvider:
    """VdoCipher when VDOCIPHER_API_SECRET is set, otherwise the in-memory mock.

    Used as a FastAPI dependency, so tests can swap it via app.dependency_overrides.
    """
    settings = get_settings()
    if settings.vdocipher_api_secret:
        return VdoCipherProvider(settings.vdocipher_api_secret, settings.vdocipher_api_base_url)
    if settings.environment == "production":
        raise RuntimeError("VDOCIPHER_API_SECRET is empty: refusing to serve videos without DRM in production")
    logger.warning("VDOCIPHER_API_SECRET is empty -> MockVideoProvider is used (no real DRM, dev only)")
    return MockVideoProvider(
        auto_ready=True,
        upload_base_url=settings.mock_video_upload_url or None,
        processing_seconds=settings.mock_video_processing_seconds,
    )
