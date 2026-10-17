"""In-memory fake of VdoCipher for development and tests. NO real DRM!

It builds the OTP request exactly like the real VdoCipher provider (same watermark code)
and remembers it in `otp_requests`, so tests can check what would be sent.
"""

import base64
import json
import secrets
import time
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

    def __init__(
        self, *, auto_ready: bool = False, upload_base_url: str | None = None, processing_seconds: float = 0
    ) -> None:
        # auto_ready=True (dev server): a video that finished "uploading" reports "ready" when asked.
        # Without upload_base_url nothing can be uploaded, so then even "uploading" videos turn ready,
        # and the whole flow can still be clicked through in /docs.
        self.auto_ready = auto_ready
        # upload_base_url (dev server): browsers really POST the file there (see app/api/routes/dev.py),
        # so the teacher panel's upload + progress bar work without VdoCipher.
        self.upload_base_url = upload_base_url.rstrip("/") if upload_base_url else None
        self.upload_tokens: dict[str, str] = {}
        # Simulated encoding time: an auto_ready video stays "processing" this long (dev/manual tests)
        self.processing_seconds = processing_seconds
        self.ready_at: dict[str, float] = {}
        self.videos: dict[str, VideoInfo] = {}
        self.otp_requests: list[dict] = []
        self.deleted: list[str] = []
        self.imports: list[dict] = []
        self.fail_import = False  # test switch: simulate a provider error on import

    def set_status(self, video_id: str, status: LessonStatus, duration_seconds: int | None = None) -> None:
        """Test helper: pretend the provider finished (or failed) processing."""
        self.videos[video_id] = VideoInfo(status=status, duration_seconds=duration_seconds)

    async def create_upload(self, *, title: str) -> UploadCredentials:
        video_id = f"mock-{uuid.uuid4().hex}"
        self.videos[video_id] = VideoInfo(status=LessonStatus.UPLOADING)
        if self.upload_base_url:
            token = secrets.token_urlsafe(24)
            self.upload_tokens[video_id] = token
            return UploadCredentials(
                video_id=video_id,
                upload_url=f"{self.upload_base_url}/{video_id}?token={token}",
                fields={"key": video_id},
            )
        return UploadCredentials(
            video_id=video_id,
            upload_url=f"https://mock-video.invalid/upload/{video_id}",
            fields={"key": video_id, "policy": "mock-policy"},
        )

    def accept_upload(self, video_id: str, token: str) -> bool:
        """Called by the dev upload endpoint once the file arrived. One-time token."""
        expected = self.upload_tokens.get(video_id)
        if not expected or not secrets.compare_digest(expected, token):
            return False
        del self.upload_tokens[video_id]
        self.videos[video_id] = VideoInfo(status=LessonStatus.PROCESSING)
        self.ready_at[video_id] = time.monotonic() + self.processing_seconds
        return True

    async def import_from_url(self, *, url: str, title: str) -> str:
        if self.fail_import:
            raise VideoProviderError("Mock: import failed")
        video_id = f"mock-{uuid.uuid4().hex}"
        self.imports.append({"video_id": video_id, "url": url, "title": title})
        self.videos[video_id] = VideoInfo(status=LessonStatus.PROCESSING)
        self.ready_at[video_id] = time.monotonic() + self.processing_seconds
        return video_id

    async def get_video_info(self, video_id: str) -> VideoInfo | None:
        info = self.videos.get(video_id)
        promotable = {LessonStatus.PROCESSING} if self.upload_base_url else {LessonStatus.UPLOADING, LessonStatus.PROCESSING}
        still_encoding = time.monotonic() < self.ready_at.get(video_id, 0)
        if info is not None and self.auto_ready and info.status in promotable and not still_encoding:
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
