import uuid

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import ClientIp, DbSession, LiveProviderDep, RecordingStorageDep, TeacherAuth, VideoProviderDep
from app.models import LiveSession
from app.schemas.live import (
    ClientOptions,
    LiveSessionCreate,
    LiveSessionOut,
    LiveSessionUpdate,
    TeacherLiveTokenOut,
)
from app.services import lesson_service, live_service

router = APIRouter(prefix="/teacher", tags=["teacher live sessions"])


@router.post("/courses/{course_id}/live-sessions", response_model=LiveSessionOut, status_code=201)
async def schedule_live_session(
    course_id: uuid.UUID, body: LiveSessionCreate, auth: TeacherAuth, db: DbSession, ip: ClientIp
):
    return await live_service.create(
        db, teacher=auth.user, course_id=course_id, title=body.title, scheduled_at=body.scheduled_at, ip=ip
    )


@router.get("/courses/{course_id}/live-sessions", response_model=list[LiveSessionOut])
async def list_live_sessions(course_id: uuid.UUID, auth: TeacherAuth, db: DbSession):
    course = await lesson_service.get_own_course(db, teacher=auth.user, course_id=course_id)
    return list(
        await db.scalars(
            select(LiveSession).where(LiveSession.course_id == course.id).order_by(LiveSession.scheduled_at.desc())
        )
    )


@router.get("/live-sessions/{live_session_id}", response_model=LiveSessionOut)
async def get_live_session(live_session_id: uuid.UUID, auth: TeacherAuth, db: DbSession):
    live = await live_service.get_own(db, teacher=auth.user, live_session_id=live_session_id)
    await db.commit()  # release the row lock
    return live


@router.patch("/live-sessions/{live_session_id}", response_model=LiveSessionOut)
async def update_live_session(
    live_session_id: uuid.UUID, body: LiveSessionUpdate, auth: TeacherAuth, db: DbSession, ip: ClientIp
):
    """Only while the session is still `scheduled`."""
    return await live_service.update(
        db, teacher=auth.user, live_session_id=live_session_id, changes=body.model_dump(exclude_unset=True), ip=ip
    )


@router.post("/live-sessions/{live_session_id}/cancel", response_model=LiveSessionOut)
async def cancel_live_session(live_session_id: uuid.UUID, auth: TeacherAuth, db: DbSession, ip: ClientIp):
    return await live_service.cancel(db, teacher=auth.user, live_session_id=live_session_id, ip=ip)


@router.post("/live-sessions/{live_session_id}/start", response_model=TeacherLiveTokenOut)
async def start_live_session(
    live_session_id: uuid.UUID,
    auth: TeacherAuth,
    db: DbSession,
    ip: ClientIp,
    live_provider: LiveProviderDep,
    storage: RecordingStorageDep,
):
    """Opens the room, starts recording AUTOMATICALLY and returns a token with publish rights.

    Safe to call again while live (app restart / reconnect): returns a fresh token only.
    """
    live, token, ttl = await live_service.start(
        db, teacher=auth.user, live_session_id=live_session_id, live_provider=live_provider, storage=storage, ip=ip
    )
    return TeacherLiveTokenOut(
        live_session=LiveSessionOut.model_validate(live),
        url=live_provider.url,
        token=token,
        expires_in=ttl,
        client_options=ClientOptions(**live_service.CLIENT_OPTIONS),
    )


@router.post("/live-sessions/{live_session_id}/end", response_model=LiveSessionOut)
async def end_live_session(
    live_session_id: uuid.UUID, auth: TeacherAuth, db: DbSession, ip: ClientIp, live_provider: LiveProviderDep
):
    """Stops the recording and closes the room. The recording becomes a lesson automatically."""
    return await live_service.end(
        db, teacher=auth.user, live_session_id=live_session_id, live_provider=live_provider, ip=ip
    )


@router.post("/live-sessions/{live_session_id}/recording/retry", response_model=LiveSessionOut)
async def retry_recording(
    live_session_id: uuid.UUID,
    auth: TeacherAuth,
    db: DbSession,
    ip: ClientIp,
    live_provider: LiveProviderDep,
    video: VideoProviderDep,
    storage: RecordingStorageDep,
):
    """After `recording_status=failed`: restarts the recorder (lesson still live) or resumes
    processing the saved file from the step that failed."""
    return await live_service.retry_recording(
        db,
        teacher=auth.user,
        live_session_id=live_session_id,
        live_provider=live_provider,
        video=video,
        storage=storage,
        ip=ip,
    )
