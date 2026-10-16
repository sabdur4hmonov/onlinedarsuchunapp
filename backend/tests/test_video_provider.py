"""Checks the REAL VdoCipher provider code against a fake HTTP server (httpx.MockTransport):
right URLs, auth header, OTP body with watermark. No network, no API key needed."""

import json

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.models import LessonStatus
from app.services.video import VdoCipherProvider, VideoProviderError, Watermark


def _provider(handler) -> VdoCipherProvider:
    return VdoCipherProvider("secret-123", "https://dev.vdocipher.com/api", transport=httpx.MockTransport(handler))


async def test_vdocipher_otp_request_shape():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"], seen["url"] = request.method, str(request.url)
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"otp": "otp-1", "playbackInfo": "info-1"})

    creds = await _provider(handler).create_playback(
        "vid-42", ttl_seconds=300, watermark=Watermark(user_id="user-uuid", phone="+998901234567")
    )
    assert (creds.otp, creds.playback_info, creds.expires_in) == ("otp-1", "info-1", 300)
    assert seen["method"] == "POST"
    assert seen["url"] == "https://dev.vdocipher.com/api/videos/vid-42/otp"
    assert seen["auth"] == "Apisecret secret-123"
    assert seen["body"]["ttl"] == 300
    annotation = json.loads(seen["body"]["annotate"])
    assert "+998901234567" in annotation[0]["text"] and "user-uuid" in annotation[0]["text"]


async def test_vdocipher_upload_credentials_parsed():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT" and request.url.params["title"] == "1-dars"
        return httpx.Response(
            200,
            json={
                "videoId": "vid-1",
                "clientPayload": {"uploadLink": "https://s3.example/upload", "policy": "p", "key": "k"},
            },
        )

    creds = await _provider(handler).create_upload(title="1-dars")
    assert creds.video_id == "vid-1"
    assert creds.upload_url == "https://s3.example/upload"
    assert creds.fields["policy"] == "p" and "uploadLink" not in creds.fields


async def test_vdocipher_status_mapping_and_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/missing"):
            return httpx.Response(404)
        if request.url.path.endswith("/broken"):
            return httpx.Response(500)
        return httpx.Response(200, json={"status": "ready", "length": 125})

    provider = _provider(handler)
    info = await provider.get_video_info("ok")
    assert info.status == LessonStatus.READY and info.duration_seconds == 125
    assert await provider.get_video_info("missing") is None
    with pytest.raises(VideoProviderError):
        await provider.get_video_info("broken")


def test_otp_ttl_cannot_exceed_five_minutes():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="x", jwt_secret="x" * 32, playback_otp_ttl_seconds=301)
