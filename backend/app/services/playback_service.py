"""Issuing video playback permission to a student.

By the time we get here, `get_current_auth` (rule 5) already proved: valid token,
session not revoked, X-Device-ID matches the session, device still bound.
This module adds the lesson-level checks and asks the provider for a short-lived OTP.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import api_error
from app.models import Course, Enrollment, EnrollmentStatus, Lesson, LessonStatus, User, UserSession
from app.schemas.lesson import PlaybackOut
from app.services import consent_service
from app.services.audit import AuditEvent, log_event
from app.services.video import VideoProvider, VideoProviderError, Watermark


async def deny(
    db: AsyncSession,
    *,
    user: User,
    session: UserSession,
    lesson_id: uuid.UUID,
    ip: str | None,
    reason: str,
    status_code: int,
    code: str,
    message: str,
    **extra,
):
    """Every refused playback request is audited too, then turned into an HTTP error."""
    log_event(
        db,
        AuditEvent.PLAYBACK_DENIED,
        user_id=user.id,
        ip=ip,
        lesson_id=lesson_id,
        device_id=session.device_id,
        reason=reason,
    )
    await db.commit()
    return api_error(status_code, code, message, **extra)


async def issue_playback(
    db: AsyncSession,
    *,
    user: User,
    session: UserSession,
    lesson_id: uuid.UUID,
    provider: VideoProvider,
    ip: str | None,
) -> PlaybackOut:
    settings = get_settings()
    ctx = {"user": user, "session": session, "lesson_id": lesson_id, "ip": ip}

    missing = await consent_service.missing_for_content(db, user.id)
    if missing:
        raise await deny(
            db,
            **ctx,
            reason="consent_required",
            status_code=403,
            code="consent_required",
            message="Videoni ko'rish uchun kamera va ma'lumotlardan foydalanishga rozilik bering",
            missing=[m.value for m in missing],
        )

    lesson = await db.get(Lesson, lesson_id)
    if lesson is None:
        raise await deny(
            db, **ctx, reason="lesson_not_found", status_code=404, code="lesson_not_found", message="Dars topilmadi"
        )

    enrolled = await db.scalar(
        select(Enrollment.student_id)
        .join(Course, Course.id == Enrollment.course_id)
        .where(
            Course.id == lesson.course_id,
            Enrollment.student_id == user.id,
            Enrollment.status == EnrollmentStatus.ACTIVE,
        )
    )
    if enrolled is None:
        raise await deny(
            db, **ctx, reason="not_enrolled", status_code=403, code="not_enrolled", message="Siz bu kursga yozilmagansiz"
        )

    if lesson.status != LessonStatus.READY or not lesson.provider_video_id or lesson.provider != provider.name:
        raise await deny(
            db,
            **ctx,
            reason=f"lesson_not_ready:{lesson.status}" if lesson.provider in (None, provider.name) else "provider_mismatch",
            status_code=409,
            code="lesson_not_ready",
            message="Dars videosi hali tayyor emas",
        )

    try:
        credentials = await provider.create_playback(
            lesson.provider_video_id,
            ttl_seconds=min(settings.playback_otp_ttl_seconds, 300),
            watermark=Watermark(user_id=str(user.id), phone=user.phone),
        )
    except VideoProviderError:
        raise await deny(
            db,
            **ctx,
            reason="provider_error",
            status_code=502,
            code="video_provider_error",
            message="Video servisi bilan bog'lanib bo'lmadi, birozdan keyin urinib ko'ring",
        ) from None

    log_event(
        db,
        AuditEvent.PLAYBACK_GRANTED,
        user_id=user.id,
        ip=ip,
        lesson_id=lesson.id,
        course_id=lesson.course_id,
        device_id=session.device_id,
        session_id=session.id,
        provider=provider.name,
        ttl_seconds=credentials.expires_in,
    )
    await db.commit()
    return PlaybackOut(
        provider=provider.name,
        otp=credentials.otp,
        playback_info=credentials.playback_info,
        expires_in=credentials.expires_in,
    )
