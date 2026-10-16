"""Provider-independent video interface.

The rest of the app talks only to `VideoProvider`. To switch from VdoCipher to another
DRM service, write one new class implementing these methods and select it in
app/services/video/__init__.py — routes, services and tests stay the same.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.models import LessonStatus


class VideoProviderError(Exception):
    """The provider API failed or answered with an error."""


@dataclass(frozen=True)
class UploadCredentials:
    """What the teacher's client needs to upload the file DIRECTLY to the provider.

    The client sends a multipart POST to `upload_url` with all `fields` and the file
    as the last field named "file". The video never passes through our server.
    """

    video_id: str
    upload_url: str
    fields: dict[str, str]


@dataclass(frozen=True)
class VideoInfo:
    status: LessonStatus
    duration_seconds: int | None = None


@dataclass(frozen=True)
class Watermark:
    """Who is watching. Shown over the video so a leaked recording points to its source."""

    user_id: str
    phone: str  # full number, deliberately not masked

    def text(self) -> str:
        return f"{self.phone} | ID: {self.user_id}"


@dataclass(frozen=True)
class PlaybackCredentials:
    otp: str
    playback_info: str
    expires_in: int  # seconds


class VideoProvider(ABC):
    name: str

    @abstractmethod
    async def create_upload(self, *, title: str) -> UploadCredentials: ...

    @abstractmethod
    async def import_from_url(self, *, url: str, title: str) -> str:
        """Provider downloads the file itself from `url` (e.g. a presigned S3 link). Returns the video ID."""

    @abstractmethod
    async def get_video_info(self, video_id: str) -> VideoInfo | None:
        """Current status straight from the provider. None if the video does not exist."""

    @abstractmethod
    async def create_playback(self, video_id: str, *, ttl_seconds: int, watermark: Watermark) -> PlaybackCredentials:
        """Short-lived playback permission with a dynamic watermark burned into the player."""

    @abstractmethod
    async def delete_video(self, video_id: str) -> None: ...

    @abstractmethod
    def parse_webhook(self, payload: dict) -> str | None:
        """Video ID the webhook is about (None if the payload is not understood).

        Only the ID is taken from the webhook body; the status is always re-fetched
        from the provider API, so a forged body can never mark a video as ready.
        """
