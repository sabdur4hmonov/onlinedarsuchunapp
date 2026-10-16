import uuid

from fastapi import APIRouter

from app.api.deps import ClientIp, DbSession, StudentAuth, VideoProviderDep, playback_rate_limiter
from app.schemas.lesson import PlaybackOut
from app.services import playback_service

router = APIRouter(prefix="/lessons", tags=["student lessons"])


@router.post("/{lesson_id}/playback", response_model=PlaybackOut)
async def lesson_playback(
    lesson_id: uuid.UUID, auth: StudentAuth, db: DbSession, ip: ClientIp, provider: VideoProviderDep
):
    """Short-lived (max 5 min) permission to play one lesson.

    Checked: active session + bound device + matching X-Device-ID (401), rate limit (429),
    consent (403), enrollment (403), lesson ready (409). The video carries a moving
    watermark with the student's phone number and ID. Every request is audited.
    """
    if not await playback_rate_limiter.hit(f"playback-user:{auth.user.id}"):
        raise await playback_service.deny(
            db,
            user=auth.user,
            session=auth.session,
            lesson_id=lesson_id,
            ip=ip,
            reason="rate_limited",
            status_code=429,
            code="too_many_attempts",
            message="Juda ko'p so'rov. Bir daqiqadan keyin qayta urinib ko'ring",
        )
    return await playback_service.issue_playback(
        db, user=auth.user, session=auth.session, lesson_id=lesson_id, provider=provider, ip=ip
    )
