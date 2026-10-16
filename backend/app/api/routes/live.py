import uuid

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import ClientIp, DbSession, LiveProviderDep, StudentAuth, live_join_rate_limiter
from app.core.errors import api_error
from app.models import Enrollment, EnrollmentStatus, LiveSession, LiveSessionStatus
from app.schemas.live import ClientOptions, LiveSessionPublicOut, StudentJoinOut, WatermarkOut
from app.services import live_service
from app.services.video import Watermark

router = APIRouter(tags=["student live sessions"])


@router.get("/courses/{course_id}/live-sessions", response_model=list[LiveSessionPublicOut])
async def course_live_sessions(course_id: uuid.UUID, auth: StudentAuth, db: DbSession):
    """Upcoming and currently running live lessons of a course the student is enrolled in."""
    enrolled = await db.scalar(
        select(Enrollment.student_id).where(
            Enrollment.course_id == course_id,
            Enrollment.student_id == auth.user.id,
            Enrollment.status == EnrollmentStatus.ACTIVE,
        )
    )
    if enrolled is None:
        raise api_error(404, "course_not_found", "Kurs topilmadi yoki siz unga yozilmagansiz")
    return list(
        await db.scalars(
            select(LiveSession)
            .where(
                LiveSession.course_id == course_id,
                LiveSession.status.in_([LiveSessionStatus.SCHEDULED, LiveSessionStatus.LIVE]),
            )
            .order_by(LiveSession.scheduled_at)
        )
    )


@router.post("/live-sessions/{live_session_id}/join", response_model=StudentJoinOut)
async def join_live_session(
    live_session_id: uuid.UUID, auth: StudentAuth, db: DbSession, ip: ClientIp, live_provider: LiveProviderDep
):
    """Subscribe-only LiveKit token (no camera/microphone/screen/data publishing), valid 10 minutes for joining.

    Checked: session + bound device + X-Device-ID (401), rate limit (429), consent (403),
    enrollment (403), session is live (409). LiveKit identity = user ID, so a second
    connection of the same account kicks out the first one. Every request is audited.
    """
    if not await live_join_rate_limiter.hit(f"live-join-user:{auth.user.id}"):
        raise await live_service.deny_join(
            db,
            user=auth.user,
            session=auth.session,
            live_session_id=live_session_id,
            ip=ip,
            reason="rate_limited",
            status_code=429,
            code="too_many_attempts",
            message="Juda ko'p so'rov. Bir daqiqadan keyin qayta urinib ko'ring",
        )
    live, token, ttl = await live_service.join(
        db, user=auth.user, session=auth.session, live_session_id=live_session_id, live_provider=live_provider, ip=ip
    )
    watermark = Watermark(user_id=str(auth.user.id), phone=auth.user.phone)
    return StudentJoinOut(
        live_session=LiveSessionPublicOut.model_validate(live),
        url=live_provider.url,
        token=token,
        expires_in=ttl,
        identity=str(auth.user.id),
        watermark=WatermarkOut(user_id=auth.user.id, phone=auth.user.phone, text=watermark.text()),
        client_options=ClientOptions(**live_service.CLIENT_OPTIONS),
    )
