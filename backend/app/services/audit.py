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
    LESSON_CREATED = "lesson_created"
    LESSON_UPDATED = "lesson_updated"
    LESSON_DELETED = "lesson_deleted"
    LESSONS_REORDERED = "lessons_reordered"
    VIDEO_UPLOAD_STARTED = "video_upload_started"
    VIDEO_STATUS_UPDATED = "video_status_updated"
    WEBHOOK_REJECTED = "webhook_rejected"
    PLAYBACK_GRANTED = "playback_granted"
    PLAYBACK_DENIED = "playback_denied"


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
