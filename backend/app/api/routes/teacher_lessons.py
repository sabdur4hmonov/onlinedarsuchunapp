import uuid

from fastapi import APIRouter

from app.api.deps import ClientIp, DbSession, TeacherAuth, VideoProviderDep
from app.schemas.lesson import LessonCreate, LessonOut, LessonReorder, LessonUpdate, VideoUploadOut
from app.services import lesson_service

router = APIRouter(prefix="/teacher", tags=["teacher lessons"])


@router.post("/courses/{course_id}/lessons", response_model=LessonOut, status_code=201)
async def create_lesson(course_id: uuid.UUID, body: LessonCreate, auth: TeacherAuth, db: DbSession, ip: ClientIp):
    """Adds a lesson at the end of the course. Only the course owner can do it."""
    return await lesson_service.create_lesson(
        db, teacher=auth.user, course_id=course_id, title=body.title, description=body.description, ip=ip
    )


@router.get("/courses/{course_id}/lessons", response_model=list[LessonOut])
async def list_lessons(course_id: uuid.UUID, auth: TeacherAuth, db: DbSession):
    course = await lesson_service.get_own_course(db, teacher=auth.user, course_id=course_id)
    return await lesson_service.list_lessons(db, course.id)


@router.put("/courses/{course_id}/lessons/order", response_model=list[LessonOut])
async def reorder_lessons(course_id: uuid.UUID, body: LessonReorder, auth: TeacherAuth, db: DbSession, ip: ClientIp):
    """Send ALL lesson IDs of the course in the new order."""
    return await lesson_service.reorder_lessons(
        db, teacher=auth.user, course_id=course_id, lesson_ids=body.lesson_ids, ip=ip
    )


@router.patch("/lessons/{lesson_id}", response_model=LessonOut)
async def update_lesson(lesson_id: uuid.UUID, body: LessonUpdate, auth: TeacherAuth, db: DbSession, ip: ClientIp):
    return await lesson_service.update_lesson(
        db, teacher=auth.user, lesson_id=lesson_id, changes=body.model_dump(exclude_unset=True), ip=ip
    )


@router.delete("/lessons/{lesson_id}", status_code=204)
async def delete_lesson(lesson_id: uuid.UUID, auth: TeacherAuth, db: DbSession, ip: ClientIp, provider: VideoProviderDep):
    """Deletes the lesson and its video at the provider."""
    await lesson_service.delete_lesson(db, teacher=auth.user, lesson_id=lesson_id, provider=provider, ip=ip)


@router.post("/lessons/{lesson_id}/video-upload", response_model=VideoUploadOut)
async def start_video_upload(
    lesson_id: uuid.UUID, auth: TeacherAuth, db: DbSession, ip: ClientIp, provider: VideoProviderDep
):
    """Returns one-time credentials; the client uploads the file straight to the video provider.

    When processing finishes, the provider calls our webhook and the lesson becomes `ready`.
    """
    lesson, credentials = await lesson_service.start_video_upload(
        db, teacher=auth.user, lesson_id=lesson_id, provider=provider, ip=ip
    )
    return VideoUploadOut(
        lesson=LessonOut.model_validate(lesson), upload_url=credentials.upload_url, fields=credentials.fields
    )


@router.post("/lessons/{lesson_id}/sync-status", response_model=LessonOut)
async def sync_video_status(
    lesson_id: uuid.UUID, auth: TeacherAuth, db: DbSession, ip: ClientIp, provider: VideoProviderDep
):
    """Asks the provider for the current video status (useful locally, where webhooks cannot reach you)."""
    lesson = await lesson_service.get_own_lesson(db, teacher=auth.user, lesson_id=lesson_id)
    return await lesson_service.sync_video_status(
        db, lesson=lesson, provider=provider, ip=ip, source="manual_sync", actor_id=auth.user.id
    )
