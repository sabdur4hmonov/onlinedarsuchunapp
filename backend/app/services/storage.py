"""Temporary storage for raw live-lesson recordings (S3-compatible: MinIO locally, S3/R2 in production).

The raw mp4 is NOT protected by DRM, so:
- the bucket is private (no public URLs at all);
- the video provider gets only a short-lived presigned download link;
- the file is deleted as soon as the provider reports the video as ready.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from functools import lru_cache

from app.core.config import get_settings
from app.services.live.base import S3Target

logger = logging.getLogger(__name__)


class RecordingStorageError(Exception):
    pass


class RecordingStorage(ABC):
    name: str

    @abstractmethod
    async def exists(self, key: str) -> bool: ...

    @abstractmethod
    async def presigned_get_url(self, key: str, *, ttl_seconds: int) -> str: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    def egress_target(self) -> S3Target | None:
        """Upload destination handed to the recorder (None = recording cannot be stored)."""


class S3RecordingStorage(RecordingStorage):
    name = "s3"

    def __init__(
        self, *, endpoint_url: str, egress_endpoint_url: str, bucket: str, region: str, access_key: str, secret_key: str
    ) -> None:
        import boto3
        from botocore.config import Config

        self._bucket = bucket
        self._target = S3Target(
            bucket=bucket,
            region=region,
            endpoint=egress_endpoint_url or endpoint_url,
            access_key=access_key,
            secret_key=secret_key,
        )
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path" if endpoint_url else "auto"}),
        )

    async def _run(self, fn, *args, **kwargs):
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                raise FileNotFoundError from e
            raise RecordingStorageError(f"S3 error: {e.response.get('Error', {}).get('Code')}") from e
        except BotoCoreError as e:
            raise RecordingStorageError(f"S3 error: {e.__class__.__name__}") from e

    async def exists(self, key: str) -> bool:
        try:
            await self._run(self._client.head_object, Bucket=self._bucket, Key=key)
            return True
        except FileNotFoundError:
            return False

    async def presigned_get_url(self, key: str, *, ttl_seconds: int) -> str:
        return await self._run(
            self._client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=ttl_seconds,
        )

    async def delete(self, key: str) -> None:
        await self._run(self._client.delete_object, Bucket=self._bucket, Key=key)

    def egress_target(self) -> S3Target | None:
        return self._target


class MockRecordingStorage(RecordingStorage):
    """In-memory fake. Tests call `put()` to simulate the recorder writing a file."""

    name = "mock"

    def __init__(self) -> None:
        self.objects: dict[str, int] = {}
        self.deleted: list[str] = []
        self.presigned: list[dict] = []
        self.fail_delete = False

    def put(self, key: str, size: int = 1024) -> None:
        self.objects[key] = size

    async def exists(self, key: str) -> bool:
        return key in self.objects

    async def presigned_get_url(self, key: str, *, ttl_seconds: int) -> str:
        self.presigned.append({"key": key, "ttl_seconds": ttl_seconds})
        return f"https://mock-storage.invalid/recordings/{key}?X-Amz-Expires={ttl_seconds}&X-Amz-Signature=mock"

    async def delete(self, key: str) -> None:
        if self.fail_delete:
            raise RecordingStorageError("Mock: delete failed")
        self.objects.pop(key, None)
        self.deleted.append(key)

    def egress_target(self) -> S3Target | None:
        return None


@lru_cache
def get_recording_storage() -> RecordingStorage:
    settings = get_settings()
    if settings.recordings_storage_configured:
        return S3RecordingStorage(
            endpoint_url=settings.recordings_s3_endpoint_url,
            egress_endpoint_url=settings.recordings_s3_egress_endpoint_url,
            bucket=settings.recordings_s3_bucket,
            region=settings.recordings_s3_region,
            access_key=settings.recordings_s3_access_key,
            secret_key=settings.recordings_s3_secret_key,
        )
    if settings.environment == "production":
        raise RuntimeError("Recording storage (RECORDINGS_S3_*) is not configured in production")
    logger.warning("RECORDINGS_S3_* settings are empty -> in-memory MockRecordingStorage is used (dev only)")
    return MockRecordingStorage()
