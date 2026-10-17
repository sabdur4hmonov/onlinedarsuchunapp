"""Inspects the raw recording of one live session (used by the panel's real-recording test).

    python scripts/check_recording.py <live_session_id>

Prints JSON: the session's statuses, objects in the temporary bucket (size, real mp4 structure,
duration from the 'mvhd' box) and the recording-related audit events.
"""

import asyncio
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boto3  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402


def mp4_info(data: bytes) -> dict:
    """Top-level boxes + duration (seconds) from moov/mvhd."""
    boxes, pos, duration = [], 0, None
    while pos + 8 <= len(data):
        size, kind = struct.unpack(">I4s", data[pos : pos + 8])
        if size == 1:
            size = struct.unpack(">Q", data[pos + 8 : pos + 16])[0]
        if size < 8:
            break
        name = kind.decode("latin-1")
        boxes.append(name)
        if name == "moov":
            mvhd = data.find(b"mvhd", pos, pos + size)
            if mvhd > 0:
                version = data[mvhd + 4]
                if version == 1:
                    timescale, dur = struct.unpack(">IQ", data[mvhd + 24 : mvhd + 36])
                else:
                    timescale, dur = struct.unpack(">II", data[mvhd + 16 : mvhd + 24])
                duration = round(dur / timescale, 1) if timescale else None
        pos += size
    return {"boxes": boxes, "duration_seconds": duration}


async def db_part(session_id: str) -> dict:
    async with SessionLocal() as db:
        row = (
            await db.execute(
                text(
                    "SELECT status, recording_status, recording_error, recording_object_key, resulting_lesson_id "
                    "FROM live_sessions WHERE id = :id"
                ),
                {"id": session_id},
            )
        ).mappings().first()
        events = (
            await db.execute(
                text(
                    "SELECT event_type, details FROM audit_logs WHERE details->>'live_session_id' = :id ORDER BY id"
                ),
                {"id": session_id},
            )
        ).all()
    await engine.dispose()
    return {
        "session": {k: (str(v) if v is not None else None) for k, v in (row or {}).items()},
        "events": [e for e, _ in events],
        "failures": [d for e, d in events if e == "recording_failed"],
    }


def main(session_id: str) -> None:
    s = get_settings()
    s3 = boto3.client(
        "s3",
        endpoint_url=s.recordings_s3_endpoint_url or None,
        region_name=s.recordings_s3_region,
        aws_access_key_id=s.recordings_s3_access_key,
        aws_secret_access_key=s.recordings_s3_secret_key,
    )
    objects = []
    listing = s3.list_objects_v2(Bucket=s.recordings_s3_bucket, Prefix=f"recordings/{session_id}/")
    for obj in listing.get("Contents", []):
        data = s3.get_object(Bucket=s.recordings_s3_bucket, Key=obj["Key"])["Body"].read()
        objects.append({"key": obj["Key"], "size": obj["Size"], **mp4_info(data)})
    print(json.dumps({"objects": objects, **asyncio.run(db_part(session_id))}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1])
