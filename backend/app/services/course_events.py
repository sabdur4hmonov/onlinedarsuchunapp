"""Course-level security journal for the teacher panel.

Collects the audit events a teacher needs to see about ONE of their courses:
problems with their students' accounts (denied logins, device conflicts, token theft),
device resets, video playback and live-lesson joins, recording failures.
"""

import uuid

from sqlalchemy import String, and_, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import AuditLog, Enrollment, Lesson, LiveSession, User
from app.services.audit import AuditEvent

# Account-level events of a student: shown in every course the student is enrolled in
STUDENT_ACCOUNT_EVENTS = {
    AuditEvent.LOGIN_FAILED,
    AuditEvent.LOGIN_DENIED,
    AuditEvent.DEVICE_ALREADY_BOUND_TO_OTHER_ACCOUNT,
    AuditEvent.REFRESH_TOKEN_REUSE_DETECTED,
    AuditEvent.DEVICE_BOUND,
    AuditEvent.CONSENT_GRANTED,
}

# Events that carry a course / lesson / live-session reference in `details`
COURSE_SCOPED_EVENTS = {
    AuditEvent.PLAYBACK_GRANTED,
    AuditEvent.PLAYBACK_DENIED,
    AuditEvent.LIVE_JOIN_GRANTED,
    AuditEvent.LIVE_JOIN_DENIED,
    AuditEvent.LIVE_SESSION_STARTED,
    AuditEvent.LIVE_SESSION_ENDED,
    AuditEvent.RECORDING_FAILED,
    AuditEvent.RECORDING_READY,
}

ALL_EVENTS = sorted(e.value for e in STUDENT_ACCOUNT_EVENTS | COURSE_SCOPED_EVENTS | {AuditEvent.DEVICE_RESET})


async def list_course_events(
    db: AsyncSession,
    course_id: uuid.UUID,
    *,
    limit: int,
    before_id: int | None,
    event_types: list[str] | None = None,
) -> list[tuple[AuditLog, User | None]]:
    student_ids = select(Enrollment.student_id).where(Enrollment.course_id == course_id)
    # `details` is JSONB with IDs stored as text, so compare against text versions of the IDs
    student_ids_text = select(cast(Enrollment.student_id, String)).where(Enrollment.course_id == course_id)
    lesson_ids_text = select(cast(Lesson.id, String)).where(Lesson.course_id == course_id)
    live_ids_text = select(cast(LiveSession.id, String)).where(LiveSession.course_id == course_id)
    details = AuditLog.details

    condition = or_(
        and_(AuditLog.event_type.in_([e.value for e in STUDENT_ACCOUNT_EVENTS]), AuditLog.user_id.in_(student_ids)),
        and_(
            AuditLog.event_type.in_([e.value for e in COURSE_SCOPED_EVENTS]),
            or_(
                details["course_id"].astext == str(course_id),
                details["lesson_id"].astext.in_(lesson_ids_text),
                details["live_session_id"].astext.in_(live_ids_text),
            ),
        ),
        and_(
            AuditLog.event_type == AuditEvent.DEVICE_RESET.value,
            details["student_id"].astext.in_(student_ids_text),
        ),
    )
    actor = aliased(User)
    stmt = select(AuditLog, actor).outerjoin(actor, actor.id == AuditLog.user_id).where(condition)
    if event_types:
        stmt = stmt.where(AuditLog.event_type.in_(event_types))
    if before_id is not None:
        stmt = stmt.where(AuditLog.id < before_id)
    rows = await db.execute(stmt.order_by(AuditLog.id.desc()).limit(limit))
    return [(log, user) for log, user in rows.all()]
