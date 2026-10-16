import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import api_error
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.security import ACCESS_TOKEN_TYPE, decode_token
from app.db.session import get_db
from app.models import User, UserRole, UserSession
from app.services import consent_service, device_service
from app.services.live import LiveProvider, get_live_provider
from app.services.storage import RecordingStorage, get_recording_storage
from app.services.video import VideoProvider, get_video_provider

DbSession = Annotated[AsyncSession, Depends(get_db)]
VideoProviderDep = Annotated[VideoProvider, Depends(get_video_provider)]
LiveProviderDep = Annotated[LiveProvider, Depends(get_live_provider)]
RecordingStorageDep = Annotated[RecordingStorage, Depends(get_recording_storage)]

_settings = get_settings()
login_rate_limiter = SlidingWindowRateLimiter(
    max_attempts=_settings.login_rate_limit_attempts,
    window_seconds=_settings.login_rate_limit_window_seconds,
)
playback_rate_limiter = SlidingWindowRateLimiter(
    max_attempts=_settings.playback_rate_limit_attempts,
    window_seconds=_settings.playback_rate_limit_window_seconds,
)
live_join_rate_limiter = SlidingWindowRateLimiter(
    max_attempts=_settings.live_join_rate_limit_attempts,
    window_seconds=_settings.live_join_rate_limit_window_seconds,
)

_bearer = HTTPBearer(auto_error=False)


def client_ip(request: Request) -> str | None:
    """Real client IP. X-Forwarded-For is honoured ONLY from TRUSTED_PROXY_IPS (e.g. the teacher
    panel's server, which forwards the browser's IP); otherwise anyone could fake their IP and
    dodge the login rate limit. The last entry is the one our own proxy appended."""
    peer = request.client.host if request.client else None
    if peer and peer in get_settings().trusted_proxies:
        forwarded = request.headers.get("x-forwarded-for", "")
        last = forwarded.split(",")[-1].strip()
        if last:
            return last[:45]
    return peer


ClientIp = Annotated[str | None, Depends(client_ip)]


def required_device_id(x_device_id: Annotated[str | None, Header(alias="X-Device-ID")] = None) -> str:
    """For login/refresh: the app must always say which device it is."""
    if not x_device_id or not 8 <= len(x_device_id) <= 128:
        raise api_error(400, "device_id_required", "X-Device-ID header yuborilishi shart (8-128 belgi)")
    return x_device_id


DeviceId = Annotated[str, Depends(required_device_id)]


@dataclass
class CurrentAuth:
    user: User
    session: UserSession


def _unauthorized():
    return api_error(401, "unauthorized", "Avtorizatsiyadan o'tilmagan yoki sessiya tugagan")


async def get_current_auth(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    x_device_id: Annotated[str | None, Header(alias="X-Device-ID")] = None,
) -> CurrentAuth:
    """Rule 5 — checked on EVERY protected request:
    token valid, session not revoked, X-Device-ID == the session's device, device still bound.
    Any mismatch -> 401.
    """
    if credentials is None or not x_device_id:
        raise _unauthorized()
    payload = decode_token(credentials.credentials, ACCESS_TOKEN_TYPE)
    if payload is None or payload.get("did") != x_device_id:
        raise _unauthorized()

    try:
        session_id, user_id = uuid.UUID(payload["sid"]), uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise _unauthorized() from None

    session = await db.get(UserSession, session_id)
    now = datetime.now(UTC)
    if (
        session is None
        or session.revoked_at is not None
        or session.expires_at <= now
        or session.user_id != user_id
        or session.device_id != x_device_id
    ):
        raise _unauthorized()

    user = await db.get(User, user_id)
    if user is None:
        raise _unauthorized()
    if user.role == UserRole.STUDENT and not await device_service.get_active_device(db, user.id, x_device_id):
        raise _unauthorized()

    session.last_seen_at = now
    await db.commit()
    return CurrentAuth(user=user, session=session)


Auth = Annotated[CurrentAuth, Depends(get_current_auth)]


async def require_teacher(auth: Auth) -> CurrentAuth:
    if auth.user.role != UserRole.TEACHER:
        raise api_error(403, "teacher_only", "Bu amal faqat o'qituvchilar uchun")
    return auth


async def require_student(auth: Auth) -> CurrentAuth:
    if auth.user.role != UserRole.STUDENT:
        raise api_error(403, "student_only", "Bu amal faqat o'quvchilar uchun")
    return auth


async def require_content_consent(db: DbSession, auth: Annotated[CurrentAuth, Depends(require_student)]) -> CurrentAuth:
    """Course content is closed until the student agreed to camera + data processing."""
    missing = await consent_service.missing_for_content(db, auth.user.id)
    if missing:
        raise api_error(
            403,
            "consent_required",
            "Kurs kontentini ko'rish uchun kamera va ma'lumotlardan foydalanishga rozilik bering",
            missing=[m.value for m in missing],
        )
    return auth


TeacherAuth = Annotated[CurrentAuth, Depends(require_teacher)]
StudentAuth = Annotated[CurrentAuth, Depends(require_student)]
ContentAuth = Annotated[CurrentAuth, Depends(require_content_consent)]
