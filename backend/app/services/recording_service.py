"""Live recording -> protected video lesson.

    teacher starts lesson ──> egress records mp4 into the private temporary bucket
    egress_ended webhook ──> new lesson is created, video provider imports the mp4
                             through a short-lived presigned URL
    video ready (webhook) ─> raw mp4 is DELETED from temporary storage

Every step is idempotent: on failure `recording_status=failed`, the reason goes to
`recording_error` + audit_logs, and the teacher's retry endpoint resumes from the
step that failed (`process_recording`).
"""

import uuid
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Lesson, LessonStatus, LiveSession, LiveSessionStatus, RecordingStatus
from app.services import lesson_service
from app.services.audit import AuditEvent, log_event
from app.services.live import LiveProvider, LiveProviderError
from app.services.storage import RecordingStorage, RecordingStorageError
from app.services.video import VideoProvider, VideoProviderError

# Uzbekistan: UTC+5, no daylight saving time
UZ_TIME = timezone(timedelta(hours=5))


def fail(
    db: AsyncSession, live: LiveSession, *, step: str, reason: str, ip: str | None = None, actor_id: uuid.UUID | None = None
) -> None:
    """Marks the recording as failed. Caller commits."""
    live.recording_status = RecordingStatus.FAILED
    live.recording_error = f"{step}: {reason}"[:512]
    log_event(
        db,
        AuditEvent.RECORDING_FAILED,
        user_id=actor_id,
        ip=ip,
        live_session_id=live.id,
        teacher_id=live.teacher_id,
        step=step,
        reason=reason,
    )


async def start_recording(
    db: AsyncSession,
    live: LiveSession,
    *,
    live_provider: LiveProvider,
    storage: RecordingStorage,
    ip: str | None,
    actor_id: uuid.UUID | None,
) -> bool:
    """Starts room-composite mp4 recording. A failure here does not stop the live lesson."""
    object_key = f"recordings/{live.id}/{uuid.uuid4().hex}.mp4"
    try:
        egress_id = await live_provider.start_recording(
            live.room_name, object_key=object_key, target=storage.egress_target()
        )
    except LiveProviderError as e:
        fail(db, live, step="egress_start", reason=str(e), ip=ip, actor_id=actor_id)
        return False
    live.egress_id = egress_id
    live.recording_object_key = object_key
    live.recording_status = RecordingStatus.RECORDING
    live.recording_error = None
    log_event(
        db, AuditEvent.RECORDING_STARTED, user_id=actor_id, ip=ip, live_session_id=live.id, egress_id=egress_id
    )
    return True


async def handle_egress_ended(
    db: AsyncSession,
    *,
    egress_id: str,
    completed: bool,
    egress_status: str,
    error: str,
    video: VideoProvider,
    storage: RecordingStorage,
    ip: str | None,
) -> LiveSession | None:
    """LiveKit says the recorder stopped. Commits."""
    live = await db.scalar(select(LiveSession).where(LiveSession.egress_id == egress_id).with_for_update())
    if live is None or live.recording_status in (RecordingStatus.PROCESSING, RecordingStatus.READY):
        return live  # not ours, or a duplicate delivery of the same event
    if not completed:
        fail(db, live, step="egress", reason=f"{egress_status}: {error or 'no details'}", ip=ip)
    else:
        live.recording_status = RecordingStatus.UPLOADING
        await process_recording(db, live, video=video, storage=storage, ip=ip)
    await db.commit()
    return live


def _recording_title(live: LiveSession) -> str:
    when = (live.started_at or live.scheduled_at).astimezone(UZ_TIME)
    return f"{live.title} — {when:%d.%m.%Y}"[:255]


async def process_recording(
    db: AsyncSession,
    live: LiveSession,
    *,
    video: VideoProvider,
    storage: RecordingStorage,
    ip: str | None,
    actor_id: uuid.UUID | None = None,
) -> None:
    """Moves the recording forward from wherever it stopped. Caller commits."""
    key = live.recording_object_key
    lesson = await db.get(Lesson, live.resulting_lesson_id) if live.resulting_lesson_id else None
    needs_import = lesson is None or lesson.provider != video.name or not lesson.provider_video_id or (
        lesson.status == LessonStatus.FAILED
    )

    if needs_import:
        if not key:
            fail(db, live, step="storage", reason="no_recording_file", ip=ip, actor_id=actor_id)
            return
        try:
            if not await storage.exists(key):
                fail(db, live, step="storage", reason="recording_file_missing", ip=ip, actor_id=actor_id)
                return
            url = await storage.presigned_get_url(key, ttl_seconds=get_settings().recordings_presigned_url_ttl_seconds)
        except RecordingStorageError as e:
            fail(db, live, step="storage", reason=str(e), ip=ip, actor_id=actor_id)
            return

        if lesson is None:
            lesson = await lesson_service.append_lesson(
                db, course_id=live.course_id, title=_recording_title(live), description="Jonli dars yozuvi"
            )
            live.resulting_lesson_id = lesson.id

        try:
            video_id = await video.import_from_url(url=url, title=lesson.title)
        except VideoProviderError as e:
            fail(db, live, step="video_import", reason=str(e), ip=ip, actor_id=actor_id)
            return
        lesson.provider = video.name
        lesson.provider_video_id = video_id
        lesson.status = LessonStatus.PROCESSING
        lesson.duration_seconds = None
        # The presigned URL itself is a secret for its lifetime: never log it
        log_event(
            db,
            AuditEvent.RECORDING_IMPORTED,
            user_id=actor_id,
            ip=ip,
            live_session_id=live.id,
            lesson_id=lesson.id,
            provider=video.name,
            provider_video_id=video_id,
        )

    live.recording_status = RecordingStatus.PROCESSING
    live.recording_error = None
    # The provider may already be done (fast processing, or a retry after it finished)
    try:
        info = await video.get_video_info(lesson.provider_video_id)
    except VideoProviderError:
        info = None  # stay "processing"; the video webhook will move it on
    if info is not None:
        lesson_service.apply_video_info(lesson, info)
    await finalize(db, live, lesson, storage=storage, ip=ip, actor_id=actor_id)


async def on_lesson_video_status(db: AsyncSession, lesson: Lesson, *, storage: RecordingStorage, ip: str | None) -> None:
    """Hook after a lesson's video status changed (video webhook / manual sync). Commits."""
    live = await db.scalar(select(LiveSession).where(LiveSession.resulting_lesson_id == lesson.id).with_for_update())
    if live is None or live.recording_status not in (RecordingStatus.PROCESSING, RecordingStatus.UPLOADING):
        return
    await finalize(db, live, lesson, storage=storage, ip=ip)
    await db.commit()


async def finalize(
    db: AsyncSession,
    live: LiveSession,
    lesson: Lesson,
    *,
    storage: RecordingStorage,
    ip: str | None,
    actor_id: uuid.UUID | None = None,
) -> None:
    """When the protected video is ready, delete the unprotected mp4. Caller commits."""
    if lesson.status == LessonStatus.FAILED:
        fail(db, live, step="video_processing", reason="provider_reported_failure", ip=ip, actor_id=actor_id)
        return
    if lesson.status != LessonStatus.READY:
        return

    if live.recording_object_key:
        try:
            await storage.delete(live.recording_object_key)
        except RecordingStorageError as e:
            # Video is ready, but the raw copy is still there: must not be reported as done
            fail(db, live, step="storage_delete", reason=str(e), ip=ip, actor_id=actor_id)
            return
        log_event(
            db,
            AuditEvent.RECORDING_TEMP_FILE_DELETED,
            user_id=actor_id,
            ip=ip,
            live_session_id=live.id,
            object_key=live.recording_object_key,
        )
        live.recording_object_key = None
    live.recording_status = RecordingStatus.READY
    live.recording_error = None
    log_event(db, AuditEvent.RECORDING_READY, user_id=actor_id, ip=ip, live_session_id=live.id, lesson_id=lesson.id)


def mark_room_closed(live: LiveSession) -> None:
    """Session is over: the recorder stops together with the room."""
    live.status = LiveSessionStatus.ENDED
    live.ended_at = live.ended_at or datetime.now(UTC)
    if live.recording_status == RecordingStatus.RECORDING:
        live.recording_status = RecordingStatus.UPLOADING
