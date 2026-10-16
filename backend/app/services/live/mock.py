"""In-memory fake of LiveKit for development and tests. No real video!

Tokens are REAL LiveKit JWTs (same code as production), signed with a random
per-process secret, so tests can decode them and check the permissions.
"""

import secrets

from app.services.live.base import LiveProvider, LiveProviderError, S3Target, build_access_token


class MockLiveProvider(LiveProvider):
    name = "mock"

    def __init__(self) -> None:
        self.url = "ws://mock-livekit.invalid"
        self.api_key = "mock-livekit-key"
        self.api_secret = secrets.token_urlsafe(32)
        self.rooms: dict[str, dict] = {}
        self.deleted_rooms: list[str] = []
        self.recordings: dict[str, dict] = {}  # egress_id -> {"room_name", "object_key", "active"}
        self.fail_recording_start = False  # test switch: simulate egress start failure

    async def create_room(self, room_name: str, *, empty_timeout_seconds: int) -> None:
        self.rooms[room_name] = {"empty_timeout": empty_timeout_seconds, "departure_timeout": empty_timeout_seconds}

    async def delete_room(self, room_name: str) -> None:
        self.rooms.pop(room_name, None)
        self.deleted_rooms.append(room_name)

    async def start_recording(self, room_name: str, *, object_key: str, target: S3Target | None) -> str:
        if self.fail_recording_start:
            raise LiveProviderError("Mock: egress start failed")
        egress_id = f"EG_mock_{secrets.token_hex(8)}"
        self.recordings[egress_id] = {"room_name": room_name, "object_key": object_key, "active": True}
        return egress_id

    async def stop_recording(self, egress_id: str) -> None:
        if egress_id in self.recordings:
            self.recordings[egress_id]["active"] = False

    def create_token(self, *, room_name: str, identity: str, name: str, can_publish: bool, ttl_seconds: int) -> str:
        return build_access_token(
            api_key=self.api_key,
            api_secret=self.api_secret,
            room_name=room_name,
            identity=identity,
            name=name,
            can_publish=can_publish,
            ttl_seconds=ttl_seconds,
        )
