"""In-memory fake of VdoCipher for development and tests. NO real DRM!

It builds the OTP request exactly like the real VdoCipher provider (same watermark code)
and remembers it in `otp_requests`, so tests can check what would be sent.
"""

import base64
import json
import secrets
import uuid

from app.models import LessonStatus
from app.services.video.base import (
    PlaybackCredentials,
    UploadCredentials,
    VideoInfo,
    VideoProvider,
    VideoProviderError,
    Watermark,
)
from app.services.video.vdocipher import build_otp_body, parse_vdocipher_webhook


class MockVideoProvider(VideoProvider):
    name = "mock"

    def __init__(self, *, auto_ready: bool = False) -> None:
        # auto_ready=True (dev server): every uploaded video reports "ready" when asked,
        # so the whole flow can be clicked through in /docs without a real upload.
        self.auto_ready = auto_ready
        self.videos: dict[str, VideoInfo] = {}
        self.otp_requests: list[dict] = []
        self.deleted: list[str] = []

    def set_status(self, video_id: str, status: LessonStatus, duration_seconds: int | None = None) -> None:
        """Test helper: pretend the provider finished (or failed) processing."""
        self.videos[video_id] = VideoInfo(status=status, duration_seconds=duration_seconds)

    async def create_upload(self, *, title: str) -> UploadCredentials:
        video_id = f"mock-{uuid.uuid4().hex}"
        self.videos[video_id] = VideoInfo(status=LessonStatus.UPLOADING)
        return UploadCredentials(
            video_id=video_id,
            upload_url=f"https://mock-video.invalid/upload/{video_id}",
            fields={"key": video_id, "policy": "mock-policy"},
        )

    async def get_video_info(self, video_id: str) -> VideoInfo | None:
        info = self.videos.get(video_id)
        if info is not None and self.auto_ready and info.status != LessonStatus.READY:
            info = VideoInfo(status=LessonStatus.READY, duration_seconds=600)
            self.videos[video_id] = info
        return info

    async def create_playback(self, video_id: str, *, ttl_seconds: int, watermark: Watermark) -> PlaybackCredentials:
        if video_id not in self.videos:
            raise VideoProviderError("Mock: unknown video")
        self.otp_requests.append({"video_id": video_id, **build_otp_body(ttl_seconds=ttl_seconds, watermark=watermark)})
        playback_info = base64.b64encode(json.dumps({"videoId": video_id}).encode()).decode()
        return PlaybackCredentials(otp=f"mock-otp-{secrets.token_hex(16)}", playback_info=playback_info, expires_in=ttl_seconds)

    async def delete_video(self, video_id: str) -> None:
        self.videos.pop(video_id, None)
        self.deleted.append(video_id)

    def parse_webhook(self, payload: dict) -> str | None:
        return parse_vdocipher_webhook(payload)
