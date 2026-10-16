import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import api_error
from app.core.security import create_access_token, generate_refresh_token, hash_refresh_token
from app.models import User, UserRole, UserSession
from app.schemas.auth import TokenResponse
from app.services import device_service
from app.services.audit import AuditEvent, log_event


def _now() -> datetime:
    return datetime.now(UTC)


def _token_response(user: User, session: UserSession, refresh_token: str) -> TokenResponse:
    settings = get_settings()
    return TokenResponse(
        access_token=create_access_token(
            user_id=user.id, session_id=session.id, device_id=session.device_id, role=user.role.value
        ),
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


async def revoke_sessions(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    reason: str,
    ip: str | None,
    device_ids: list[str] | None = None,
    session_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
) -> list[uuid.UUID]:
    """Revokes all active sessions of the user (optionally only on given devices / one session)."""
    stmt = (
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=_now(), revoke_reason=reason)
        .returning(UserSession.id)
    )
    if device_ids is not None:
        stmt = stmt.where(UserSession.device_id.in_(device_ids))
    if session_id is not None:
        stmt = stmt.where(UserSession.id == session_id)
    revoked = list((await db.execute(stmt)).scalars())
    if revoked:
        log_event(
            db,
            AuditEvent.SESSION_REVOKED,
            user_id=user_id,
            ip=ip,
            reason=reason,
            session_ids=revoked,
            actor_id=actor_id or user_id,
        )
    return revoked


async def open_session(db: AsyncSession, *, user: User, device_id: str, ip: str | None) -> TokenResponse:
    """Creates a new session and commits. Call only after credentials AND device rules were checked."""
    settings = get_settings()

    # Lock the user row so two parallel logins cannot both end up with an active session
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())

    if user.role == UserRole.STUDENT:
        # Rule: a student has only ONE active session. A new login kicks out every other one.
        await revoke_sessions(db, user_id=user.id, reason="new_login", ip=ip)

    refresh_token = generate_refresh_token()
    session = UserSession(
        id=uuid.uuid4(),
        user_id=user.id,
        device_id=device_id,
        refresh_token_hash=hash_refresh_token(refresh_token),
        expires_at=_now() + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(session)
    log_event(db, AuditEvent.LOGIN_SUCCESS, user_id=user.id, ip=ip, device_id=device_id, session_id=session.id)
    await db.commit()
    return _token_response(user, session, refresh_token)


async def _reject_refresh(db: AsyncSession, *, user_id: uuid.UUID | None, ip: str | None, reason: str):
    log_event(db, AuditEvent.TOKEN_REFRESH_REJECTED, user_id=user_id, ip=ip, reason=reason)
    await db.commit()
    return api_error(401, "invalid_refresh_token", "Sessiya tugagan, qaytadan kiring")


async def refresh(db: AsyncSession, *, refresh_token: str, device_id: str, ip: str | None) -> TokenResponse:
    """Refresh token rotation: the old refresh token stops working, a new one is returned."""
    session = await db.scalar(
        select(UserSession)
        .where(UserSession.refresh_token_hash == hash_refresh_token(refresh_token))
        .with_for_update()
    )
    if session is None:
        # Unknown, already rotated, or made up
        raise await _reject_refresh(db, user_id=None, ip=ip, reason="unknown_token")
    if session.revoked_at is not None:
        raise await _reject_refresh(db, user_id=session.user_id, ip=ip, reason="session_revoked")
    if session.expires_at <= _now():
        raise await _reject_refresh(db, user_id=session.user_id, ip=ip, reason="session_expired")
    if session.device_id != device_id:
        raise await _reject_refresh(db, user_id=session.user_id, ip=ip, reason="device_mismatch")

    user = await db.get(User, session.user_id)
    if user.role == UserRole.STUDENT and not await device_service.get_active_device(db, user.id, device_id):
        raise await _reject_refresh(db, user_id=user.id, ip=ip, reason="device_not_bound")

    new_refresh_token = generate_refresh_token()
    session.refresh_token_hash = hash_refresh_token(new_refresh_token)
    session.last_seen_at = _now()
    log_event(db, AuditEvent.TOKEN_REFRESHED, user_id=user.id, ip=ip, session_id=session.id)
    await db.commit()
    return _token_response(user, session, new_refresh_token)
