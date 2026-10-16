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
    DEVICE_RESET = "device_reset"
    SESSION_REVOKED = "session_revoked"
    TOKEN_REFRESHED = "token_refreshed"
    TOKEN_REFRESH_REJECTED = "token_refresh_rejected"
    LOGOUT = "logout"
    CONSENT_GRANTED = "consent_granted"


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
