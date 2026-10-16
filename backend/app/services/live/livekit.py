"""LiveKit implementation (WebRTC SFU). Docs: https://docs.livekit.io/home/server/"""

import asyncio

import aiohttp
from livekit import api as lk
from livekit.api.twirp_client import TwirpError

from app.services.live.base import LiveProvider, LiveProviderError, S3Target, build_access_token


class LiveKitProvider(LiveProvider):
    name = "livekit"

    def __init__(self, *, url: str, api_url: str, api_key: str, api_secret: str) -> None:
        self.url = url
        self._api_url = api_url or url.replace("wss://", "https://").replace("ws://", "http://")
        self._api_key = api_key
        self._api_secret = api_secret

    async def _call(self, fn):
        try:
            async with lk.LiveKitAPI(self._api_url, self._api_key, self._api_secret) as client:
                return await fn(client)
        except (TwirpError, aiohttp.ClientError, asyncio.TimeoutError) as e:
            raise LiveProviderError(f"LiveKit request failed: {e.__class__.__name__}") from e

    async def create_room(self, room_name: str, *, empty_timeout_seconds: int) -> None:
        # Long timeouts: if the teacher's internet drops (and the room becomes empty),
        # LiveKit keeps the room and the recording, so the lesson continues after reconnect.
        await self._call(
            lambda c: c.room.create_room(
                lk.CreateRoomRequest(
                    name=room_name,
                    empty_timeout=empty_timeout_seconds,
                    departure_timeout=empty_timeout_seconds,
                )
            )
        )

    async def delete_room(self, room_name: str) -> None:
        await self._call(lambda c: c.room.delete_room(lk.DeleteRoomRequest(room=room_name)))

    async def start_recording(self, room_name: str, *, object_key: str, target: S3Target | None) -> str:
        if target is None:
            raise LiveProviderError("Recording storage (S3/MinIO) is not configured")
        output = lk.EncodedFileOutput(
            file_type=lk.EncodedFileType.MP4,
            filepath=object_key,
            s3=lk.S3Upload(
                access_key=target.access_key,
                secret=target.secret_key,
                region=target.region,
                endpoint=target.endpoint,
                bucket=target.bucket,
                force_path_style=bool(target.endpoint),  # MinIO needs path-style URLs
            ),
        )
        info = await self._call(
            lambda c: c.egress.start_room_composite_egress(
                # "speaker" layout: the active speaker / screen share large, others small
                lk.RoomCompositeEgressRequest(room_name=room_name, layout="speaker", file_outputs=[output])
            )
        )
        return info.egress_id

    async def stop_recording(self, egress_id: str) -> None:
        await self._call(lambda c: c.egress.stop_egress(lk.StopEgressRequest(egress_id=egress_id)))

    def create_token(self, *, room_name: str, identity: str, name: str, can_publish: bool, ttl_seconds: int) -> str:
        return build_access_token(
            api_key=self._api_key,
            api_secret=self._api_secret,
            room_name=room_name,
            identity=identity,
            name=name,
            can_publish=can_publish,
            ttl_seconds=ttl_seconds,
        )
