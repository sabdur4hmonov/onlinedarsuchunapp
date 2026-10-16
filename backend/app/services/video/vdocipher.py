"""VdoCipher implementation (DRM + dynamic watermark + Flutter SDK).

API docs: https://www.vdocipher.com/docs/server/
Auth header for every call: `Authorization: Apisecret <VDOCIPHER_API_SECRET>`.
"""

import json

import httpx

from app.models import LessonStatus
from app.services.video.base import (
    PlaybackCredentials,
    UploadCredentials,
    VideoInfo,
    VideoProvider,
    VideoProviderError,
    Watermark,
)


def build_annotation(watermark: Watermark) -> str:
    """VdoCipher dynamic watermark ("annotate" field of the OTP request).

    `rtext` = text that jumps to a new random position every `interval` ms.
    Semi-transparent (`alpha`), so it does not block the lesson but survives screen recording.
    """
    return json.dumps(
        [
            {
                "type": "rtext",
                "text": watermark.text(),
                "alpha": "0.50",
                "color": "0xFFFFFF",
                "size": "14",
                "interval": "5000",
            }
        ]
    )


def build_otp_body(*, ttl_seconds: int, watermark: Watermark) -> dict:
    return {"ttl": ttl_seconds, "annotate": build_annotation(watermark)}


def parse_vdocipher_webhook(payload: dict) -> str | None:
    # Expected shape: {"event": "video:ready", "payload": {"id": "<videoId>", ...}}
    inner = payload.get("payload")
    video_id = (inner.get("id") if isinstance(inner, dict) else None) or payload.get("videoId")
    return video_id if isinstance(video_id, str) and video_id else None


def map_vdocipher_status(raw: str | None) -> LessonStatus:
    value = (raw or "").strip().lower()
    if value == "ready":
        return LessonStatus.READY
    if "error" in value or "fail" in value:
        return LessonStatus.FAILED
    if value in {"pre-upload", "pre_upload", "preupload", ""}:
        return LessonStatus.UPLOADING
    return LessonStatus.PROCESSING  # "queued", "processing", ...


class VdoCipherProvider(VideoProvider):
    name = "vdocipher"

    def __init__(self, api_secret: str, base_url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._api_secret = api_secret
        self._base_url = base_url.rstrip("/")
        self._transport = transport  # tests inject httpx.MockTransport here

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = {"Authorization": f"Apisecret {self._api_secret}", "Accept": "application/json"}
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, headers=headers, timeout=15, transport=self._transport
            ) as client:
                return await client.request(method, path, **kwargs)
        except httpx.HTTPError as e:
            raise VideoProviderError(f"VdoCipher request failed: {e.__class__.__name__}") from e

    @staticmethod
    def _ensure_ok(response: httpx.Response) -> dict:
        if response.status_code >= 400:
            # Do not include the body: it may echo request data
            raise VideoProviderError(f"VdoCipher answered HTTP {response.status_code}")
        try:
            return response.json() if response.content else {}
        except ValueError as e:
            raise VideoProviderError("VdoCipher returned invalid JSON") from e

    async def create_upload(self, *, title: str) -> UploadCredentials:
        data = self._ensure_ok(await self._request("PUT", "/videos", params={"title": title}))
        try:
            payload = dict(data["clientPayload"])
            upload_url = payload.pop("uploadLink")
            video_id = data["videoId"]
        except (KeyError, TypeError) as e:
            raise VideoProviderError("Unexpected VdoCipher upload response") from e
        fields = {**payload, "success_action_status": "201", "success_action_redirect": ""}
        return UploadCredentials(video_id=video_id, upload_url=upload_url, fields=fields)

    async def import_from_url(self, *, url: str, title: str) -> str:
        # https://www.vdocipher.com/docs/server/upload/import-url/
        data = self._ensure_ok(await self._request("PUT", "/videos/importUrl", json={"url": url, "title": title}))
        video_id = data.get("id") or data.get("videoId")
        if not isinstance(video_id, str) or not video_id:
            raise VideoProviderError("Unexpected VdoCipher import response")
        return video_id

    async def get_video_info(self, video_id: str) -> VideoInfo | None:
        response = await self._request("GET", f"/videos/{video_id}")
        if response.status_code == 404:
            return None
        data = self._ensure_ok(response)
        length = data.get("length")
        return VideoInfo(
            status=map_vdocipher_status(data.get("status")),
            duration_seconds=int(length) if isinstance(length, int | float) and length > 0 else None,
        )

    async def create_playback(self, video_id: str, *, ttl_seconds: int, watermark: Watermark) -> PlaybackCredentials:
        data = self._ensure_ok(
            await self._request(
                "POST", f"/videos/{video_id}/otp", json=build_otp_body(ttl_seconds=ttl_seconds, watermark=watermark)
            )
        )
        try:
            return PlaybackCredentials(otp=data["otp"], playback_info=data["playbackInfo"], expires_in=ttl_seconds)
        except KeyError as e:
            raise VideoProviderError("Unexpected VdoCipher OTP response") from e

    async def delete_video(self, video_id: str) -> None:
        self._ensure_ok(await self._request("DELETE", "/videos", params={"videos": video_id}))

    def parse_webhook(self, payload: dict) -> str | None:
        return parse_vdocipher_webhook(payload)
