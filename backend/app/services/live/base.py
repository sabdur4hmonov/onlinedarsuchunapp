"""Provider-independent live-lesson interface (rooms, tokens, recording).

The rest of the app talks only to `LiveProvider`. LiveKit is the real implementation,
`MockLiveProvider` is used when LiveKit is not configured (dev and tests).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import timedelta

from livekit import api as lk


class LiveProviderError(Exception):
    """The live-video server failed or answered with an error."""


@dataclass(frozen=True)
class S3Target:
    """Where the recorder (egress) must upload the mp4."""

    bucket: str
    region: str
    endpoint: str  # empty = real AWS S3
    access_key: str
    secret_key: str


def build_access_token(
    *,
    api_key: str,
    api_secret: str,
    room_name: str,
    identity: str,
    name: str,
    can_publish: bool,
    ttl_seconds: int,
) -> str:
    """LiveKit join token (a JWT signed with the API secret).

    Students get `can_publish=False`: they can only watch and listen — no camera,
    microphone, screen share or data messages. Identity = our user ID, so when the
    same account joins from a second place LiveKit kicks out the first connection.
    """
    grants = lk.VideoGrants(
        room_join=True,
        room=room_name,
        can_subscribe=True,
        can_publish=can_publish,
        can_publish_data=can_publish,
        can_update_own_metadata=False,
    )
    return (
        lk.AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_name(name)
        .with_grants(grants)
        .with_ttl(timedelta(seconds=ttl_seconds))
        .to_jwt()
    )


class LiveProvider(ABC):
    name: str
    # URL the client apps connect to (ws:// or wss://)
    url: str

    @abstractmethod
    async def create_room(self, room_name: str, *, empty_timeout_seconds: int) -> None: ...

    @abstractmethod
    async def delete_room(self, room_name: str) -> None: ...

    @abstractmethod
    async def start_recording(self, room_name: str, *, object_key: str, target: S3Target | None) -> str:
        """Starts a composite mp4 recording of the whole room. Returns the egress ID."""

    @abstractmethod
    async def stop_recording(self, egress_id: str) -> None: ...

    @abstractmethod
    def create_token(
        self, *, room_name: str, identity: str, name: str, can_publish: bool, ttl_seconds: int
    ) -> str: ...
