import enum
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


class AuditEvent(enum.StrEnum):
    USER_REGISTERED = "user_registered"
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"  # wrong phone/password
    LOGIN_DENIED = "login_denied"  # correct password, but a rule forbids it (e.g. device limit)
    LOGIN_RATE_LIMITED = "login_rate_limited"
    DEVICE_BINDING_REQUIRED = "device_binding_required"
    DEVICE_BOUND = "device_bound"
    DEVICE_ALREADY_BOUND_TO_OTHER_ACCOUNT = "device_already_bound_to_other_account"
    DEVICE_RESET = "device_reset"
    SESSION_REVOKED = "session_revoked"
    TOKEN_REFRESHED = "token_refreshed"
    TOKEN_REFRESH_REJECTED = "token_refresh_rejected"
    REFRESH_TOKEN_REUSE_DETECTED = "refresh_token_reuse_detected"
    LOGOUT = "logout"
    CONSENT_GRANTED = "consent_granted"
    COURSE_CREATED = "course_created"
    COURSE_UPDATED = "course_updated"
    STUDENT_ENROLLED = "student_enrolled"
    STUDENT_REMOVED = "student_removed"
    LESSON_CREATED = "lesson_created"
    LESSON_UPDATED = "lesson_updated"
    LESSON_DELETED = "lesson_deleted"
    LESSONS_REORDERED = "lessons_reordered"
    VIDEO_UPLOAD_STARTED = "video_upload_started"
    VIDEO_STATUS_UPDATED = "video_status_updated"
    WEBHOOK_REJECTED = "webhook_rejected"
    PLAYBACK_GRANTED = "playback_granted"
    PLAYBACK_DENIED = "playback_denied"
    LIVE_SESSION_CREATED = "live_session_created"
    LIVE_SESSION_UPDATED = "live_session_updated"
    LIVE_SESSION_CANCELLED = "live_session_cancelled"
    LIVE_SESSION_STARTED = "live_session_started"
    LIVE_SESSION_ENDED = "live_session_ended"
    LIVE_TEACHER_TOKEN_ISSUED = "live_teacher_token_issued"
    LIVE_JOIN_GRANTED = "live_join_granted"
    LIVE_JOIN_DENIED = "live_join_denied"
    LIVE_ROOM_STARTED = "live_room_started"
    LIVE_ROOM_FINISHED = "live_room_finished"
    LIVE_PARTICIPANT_JOINED = "live_participant_joined"
    LIVE_PARTICIPANT_LEFT = "live_participant_left"
    LIVEKIT_WEBHOOK_REJECTED = "livekit_webhook_rejected"
    RECORDING_STARTED = "recording_started"
    RECORDING_FAILED = "recording_failed"
    RECORDING_IMPORTED = "recording_imported"
    RECORDING_READY = "recording_ready"
    RECORDING_TEMP_FILE_DELETED = "recording_temp_file_deleted"
    RECORDING_RETRY = "recording_retry"


def log_event(
    db: AsyncSession,
    event_type: AuditEvent,
    *,
    user_id: uuid.UUID | None = None,
    ip: str | None = None,
    **details,
) -> None:
    """Adds an audit record to the current transaction. The caller commits.

    Never put passwords or tokens into `details`.
    """
    db.add(AuditLog(user_id=user_id, event_type=event_type.value, ip=ip, details=_jsonable(details)))


def _jsonable(value):
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [_jsonable(v) for v in value]
    if isinstance(value, uuid.UUID | enum.Enum):
        return str(value)
    return value
