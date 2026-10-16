import logging
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import api_error
from app.models import (
    Course,
    Enrollment,
    EnrollmentStatus,
    LiveSession,
    LiveSessionStatus,
    RecordingStatus,
    User,
    UserSession,
)
from app.services import consent_service, lesson_service, recording_service
from app.services.audit import AuditEvent, log_event
from app.services.live import LiveProvider, LiveProviderError
from app.services.storage import RecordingStorage
from app.services.video import VideoProvider

logger = logging.getLogger(__name__)

# Recommended client settings (they are CLIENT options in the LiveKit SDKs, not room settings):
# adaptive stream = receive only the resolution that is actually displayed,
# dynacast = the publisher stops encoding layers nobody watches,
# simulcast = the teacher sends several qualities, weak connections get a lower one.
CLIENT_OPTIONS = {"adaptive_stream": True, "dynacast": True, "simulcast": True, "auto_subscribe": True}


def _new_room_name() -> str:
    # 192 random bits: cannot be guessed or derived from course/lesson IDs
    return f"live-{secrets.token_urlsafe(24)}"


async def create(
    db: AsyncSession, *, teacher: User, course_id: uuid.UUID, title: str, scheduled_at: datetime, ip: str | None
) -> LiveSession:
    course = await lesson_service.get_own_course(db, teacher=teacher, course_id=course_id)
    live = LiveSession(
        course_id=course.id, teacher_id=teacher.id, title=title, scheduled_at=scheduled_at, room_name=_new_room_name()
    )
    db.add(live)
    await db.flush()
    log_event(db, AuditEvent.LIVE_SESSION_CREATED, user_id=teacher.id, ip=ip, live_session_id=live.id, course_id=course.id)
    await db.commit()
    return live


async def get_own(db: AsyncSession, *, teacher: User, live_session_id: uuid.UUID) -> LiveSession:
    """Only the owner of the course may manage its live sessions (404 hides the rest)."""
    live = await db.scalar(
        select(LiveSession)
        .join(Course, Course.id == LiveSession.course_id)
        .where(LiveSession.id == live_session_id, Course.teacher_id == teacher.id)
        .with_for_update(of=LiveSession)
    )
    if live is None:
        raise api_error(404, "live_session_not_found", "Jonli dars topilmadi")
    return live


def _require_status(live: LiveSession, *allowed: LiveSessionStatus) -> None:
    if live.status not in allowed:
        raise api_error(
            409,
            "invalid_live_session_status",
            f"Bu amal uchun dars holati mos emas (hozir: {live.status})",
            status=live.status.value,
        )


async def update(db: AsyncSession, *, teacher: User, live_session_id: uuid.UUID, changes: dict, ip: str | None) -> LiveSession:
    live = await get_own(db, teacher=teacher, live_session_id=live_session_id)
    _require_status(live, LiveSessionStatus.SCHEDULED)
    for field, value in changes.items():
        setattr(live, field, value)
    log_event(db, AuditEvent.LIVE_SESSION_UPDATED, user_id=teacher.id, ip=ip, live_session_id=live.id, fields=sorted(changes))
    await db.commit()
    return live


async def cancel(db: AsyncSession, *, teacher: User, live_session_id: uuid.UUID, ip: str | None) -> LiveSession:
    live = await get_own(db, teacher=teacher, live_session_id=live_session_id)
    _require_status(live, LiveSessionStatus.SCHEDULED)
    live.status = LiveSessionStatus.CANCELLED
    log_event(db, AuditEvent.LIVE_SESSION_CANCELLED, user_id=teacher.id, ip=ip, live_session_id=live.id)
    await db.commit()
    return live


async def start(
    db: AsyncSession,
    *,
    teacher: User,
    live_session_id: uuid.UUID,
    live_provider: LiveProvider,
    storage: RecordingStorage,
    ip: str | None,
) -> tuple[LiveSession, str, int]:
    """Opens the room, starts recording automatically and returns a publisher token.

    Calling it again while the lesson is live just returns a fresh token
    (e.g. the teacher's app restarted) — the room and recording keep going.
    """
    settings = get_settings()
    live = await get_own(db, teacher=teacher, live_session_id=live_session_id)
    _require_status(live, LiveSessionStatus.SCHEDULED, LiveSessionStatus.LIVE)

    if live.status == LiveSessionStatus.SCHEDULED:
        try:
            await live_provider.create_room(live.room_name, empty_timeout_seconds=settings.live_room_empty_timeout_seconds)
        except LiveProviderError:
            raise api_error(502, "live_provider_error", "Jonli dars serveri bilan bog'lanib bo'lmadi") from None
        live.status = LiveSessionStatus.LIVE
        live.started_at = datetime.now(UTC)
        log_event(db, AuditEvent.LIVE_SESSION_STARTED, user_id=teacher.id, ip=ip, live_session_id=live.id)
        await recording_service.start_recording(
            db, live, live_provider=live_provider, storage=storage, ip=ip, actor_id=teacher.id
        )

    ttl = settings.live_teacher_token_ttl_minutes * 60
    token = live_provider.create_token(
        room_name=live.room_name, identity=str(teacher.id), name=teacher.full_name, can_publish=True, ttl_seconds=ttl
    )
    log_event(db, AuditEvent.LIVE_TEACHER_TOKEN_ISSUED, user_id=teacher.id, ip=ip, live_session_id=live.id)
    await db.commit()
    return live, token, ttl


async def end(
    db: AsyncSession, *, teacher: User, live_session_id: uuid.UUID, live_provider: LiveProvider, ip: str | None
) -> LiveSession:
    """Stops the recording and closes the room. The recording is processed when egress_ended arrives."""
    live = await get_own(db, teacher=teacher, live_session_id=live_session_id)
    _require_status(live, LiveSessionStatus.LIVE)

    if live.egress_id and live.recording_status == RecordingStatus.RECORDING:
        try:
            await live_provider.stop_recording(live.egress_id)
        except LiveProviderError:
            # Not fatal: deleting the room below also ends the recording
            logger.warning("Could not stop egress %s", live.egress_id)
    try:
        await live_provider.delete_room(live.room_name)
    except LiveProviderError:
        # Not fatal: LiveKit closes the empty room after the empty timeout anyway
        logger.warning("Could not delete room for live session %s", live.id)

    recording_service.mark_room_closed(live)
    log_event(db, AuditEvent.LIVE_SESSION_ENDED, user_id=teacher.id, ip=ip, live_session_id=live.id, source="teacher")
    await db.commit()
    return live


async def retry_recording(
    db: AsyncSession,
    *,
    teacher: User,
    live_session_id: uuid.UUID,
    live_provider: LiveProvider,
    video: VideoProvider,
    storage: RecordingStorage,
    ip: str | None,
) -> LiveSession:
    live = await get_own(db, teacher=teacher, live_session_id=live_session_id)
    if live.recording_status != RecordingStatus.FAILED:
        raise api_error(409, "recording_not_failed", "Yozuvda xato yo'q, qayta urinish kerak emas")
    log_event(
        db,
        AuditEvent.RECORDING_RETRY,
        user_id=teacher.id,
        ip=ip,
        live_session_id=live.id,
        previous_error=live.recording_error,
    )

    if live.status == LiveSessionStatus.LIVE:
        # Recorder failed while the lesson is still going: start a new recording
        await recording_service.start_recording(
            db, live, live_provider=live_provider, storage=storage, ip=ip, actor_id=teacher.id
        )
    elif live.status == LiveSessionStatus.ENDED and live.recording_object_key:
        live.recording_status = RecordingStatus.UPLOADING
        await recording_service.process_recording(db, live, video=video, storage=storage, ip=ip, actor_id=teacher.id)
    else:
        await db.commit()
        raise api_error(409, "recording_not_recoverable", "Bu dars uchun yozuv fayli yo'q, uni tiklab bo'lmaydi")
    await db.commit()
    return live


# ---------- student ----------


async def deny_join(
    db: AsyncSession,
    *,
    user: User,
    session: UserSession,
    live_session_id: uuid.UUID,
    ip: str | None,
    reason: str,
    status_code: int,
    code: str,
    message: str,
    **extra,
):
    """Every refused join is audited too, then turned into an HTTP error."""
    log_event(
        db,
        AuditEvent.LIVE_JOIN_DENIED,
        user_id=user.id,
        ip=ip,
        live_session_id=live_session_id,
        device_id=session.device_id,
        reason=reason,
    )
    await db.commit()
    return api_error(status_code, code, message, **extra)


async def join(
    db: AsyncSession,
    *,
    user: User,
    session: UserSession,
    live_session_id: uuid.UUID,
    live_provider: LiveProvider,
    ip: str | None,
) -> tuple[LiveSession, str, int]:
    """Subscribe-only token for a student. Session/device/X-Device-ID were checked by get_current_auth."""
    settings = get_settings()
    ctx = {"user": user, "session": session, "live_session_id": live_session_id, "ip": ip}

    missing = await consent_service.missing_for_content(db, user.id)
    if missing:
        raise await deny_join(
            db,
            **ctx,
            reason="consent_required",
            status_code=403,
            code="consent_required",
            message="Jonli darsga kirish uchun kamera va ma'lumotlardan foydalanishga rozilik bering",
            missing=[m.value for m in missing],
        )

    live = await db.get(LiveSession, live_session_id)
    if live is None:
        raise await deny_join(
            db, **ctx, reason="not_found", status_code=404, code="live_session_not_found", message="Jonli dars topilmadi"
        )

    enrolled = await db.scalar(
        select(Enrollment.student_id).where(
            Enrollment.course_id == live.course_id,
            Enrollment.student_id == user.id,
            Enrollment.status == EnrollmentStatus.ACTIVE,
        )
    )
    if enrolled is None:
        raise await deny_join(
            db, **ctx, reason="not_enrolled", status_code=403, code="not_enrolled", message="Siz bu kursga yozilmagansiz"
        )

    if live.status != LiveSessionStatus.LIVE:
        raise await deny_join(
            db,
            **ctx,
            reason=f"not_live:{live.status}",
            status_code=409,
            code="live_session_not_live",
            message="Jonli dars hozir efirda emas",
            status=live.status.value,
        )

    ttl = settings.live_student_token_ttl_minutes * 60
    token = live_provider.create_token(
        room_name=live.room_name, identity=str(user.id), name=user.full_name, can_publish=False, ttl_seconds=ttl
    )
    log_event(
        db,
        AuditEvent.LIVE_JOIN_GRANTED,
        user_id=user.id,
        ip=ip,
        live_session_id=live.id,
        course_id=live.course_id,
        device_id=session.device_id,
        session_id=session.id,
        ttl_seconds=ttl,
    )
    await db.commit()
    return live, token, ttl
