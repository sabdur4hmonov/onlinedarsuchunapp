import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import api_error
from app.models import Course, Lesson, LessonStatus, User
from app.services.audit import AuditEvent, log_event
from app.services.video import VideoInfo, VideoProvider, VideoProviderError

logger = logging.getLogger(__name__)


def _provider_error():
    return api_error(502, "video_provider_error", "Video servisi bilan bog'lanib bo'lmadi, birozdan keyin urinib ko'ring")


async def get_own_course(db: AsyncSession, *, teacher: User, course_id: uuid.UUID, lock: bool = False) -> Course:
    """Only the course owner may touch its lessons. 404 also hides other teachers' courses."""
    stmt = select(Course).where(Course.id == course_id, Course.teacher_id == teacher.id)
    course = await db.scalar(stmt.with_for_update() if lock else stmt)
    if course is None:
        raise api_error(404, "course_not_found", "Kurs topilmadi")
    return course


async def get_own_lesson(db: AsyncSession, *, teacher: User, lesson_id: uuid.UUID) -> Lesson:
    lesson = await db.scalar(
        select(Lesson).join(Course, Course.id == Lesson.course_id).where(Lesson.id == lesson_id, Course.teacher_id == teacher.id)
    )
    if lesson is None:
        raise api_error(404, "lesson_not_found", "Dars topilmadi")
    return lesson


async def list_lessons(db: AsyncSession, course_id: uuid.UUID, *, only_ready: bool = False) -> list[Lesson]:
    stmt = select(Lesson).where(Lesson.course_id == course_id)
    if only_ready:
        stmt = stmt.where(Lesson.status == LessonStatus.READY)
    return list(await db.scalars(stmt.order_by(Lesson.position, Lesson.created_at)))


async def create_lesson(
    db: AsyncSession, *, teacher: User, course_id: uuid.UUID, title: str, description: str | None, ip: str | None
) -> Lesson:
    # Lock the course so two parallel creates do not get the same position
    course = await get_own_course(db, teacher=teacher, course_id=course_id, lock=True)
    last = await db.scalar(select(func.max(Lesson.position)).where(Lesson.course_id == course.id))
    lesson = Lesson(course_id=course.id, title=title, description=description, position=(last or 0) + 1)
    db.add(lesson)
    await db.flush()
    log_event(db, AuditEvent.LESSON_CREATED, user_id=teacher.id, ip=ip, course_id=course.id, lesson_id=lesson.id)
    await db.commit()
    return lesson


async def update_lesson(db: AsyncSession, *, teacher: User, lesson_id: uuid.UUID, changes: dict, ip: str | None) -> Lesson:
    lesson = await get_own_lesson(db, teacher=teacher, lesson_id=lesson_id)
    for field, value in changes.items():
        setattr(lesson, field, value)
    log_event(db, AuditEvent.LESSON_UPDATED, user_id=teacher.id, ip=ip, lesson_id=lesson.id, fields=sorted(changes))
    await db.commit()
    return lesson


async def _delete_remote_video(provider: VideoProvider, lesson: Lesson) -> None:
    """Best effort: a provider hiccup must not block deleting the lesson in our DB."""
    if lesson.provider_video_id and lesson.provider == provider.name:
        try:
            await provider.delete_video(lesson.provider_video_id)
        except VideoProviderError:
            logger.warning("Could not delete video %s at %s", lesson.provider_video_id, provider.name)


async def delete_lesson(
    db: AsyncSession, *, teacher: User, lesson_id: uuid.UUID, provider: VideoProvider, ip: str | None
) -> None:
    lesson = await get_own_lesson(db, teacher=teacher, lesson_id=lesson_id)
    course_id = lesson.course_id
    await get_own_course(db, teacher=teacher, course_id=course_id, lock=True)
    await _delete_remote_video(provider, lesson)
    await db.delete(lesson)
    await db.flush()
    # Close the gap: positions stay 1..n
    for position, remaining in enumerate(await list_lessons(db, course_id), start=1):
        remaining.position = position
    log_event(
        db,
        AuditEvent.LESSON_DELETED,
        user_id=teacher.id,
        ip=ip,
        course_id=course_id,
        lesson_id=lesson_id,
        provider_video_id=lesson.provider_video_id,
    )
    await db.commit()


async def reorder_lessons(
    db: AsyncSession, *, teacher: User, course_id: uuid.UUID, lesson_ids: list[uuid.UUID], ip: str | None
) -> list[Lesson]:
    course = await get_own_course(db, teacher=teacher, course_id=course_id, lock=True)
    lessons = await list_lessons(db, course.id)
    by_id = {lesson.id: lesson for lesson in lessons}
    if len(lesson_ids) != len(set(lesson_ids)) or set(lesson_ids) != set(by_id):
        raise api_error(400, "invalid_lesson_order", "Kursdagi barcha darslar ID'larini takrorlanmasdan yuboring")
    for position, lesson_id in enumerate(lesson_ids, start=1):
        by_id[lesson_id].position = position
    log_event(db, AuditEvent.LESSONS_REORDERED, user_id=teacher.id, ip=ip, course_id=course.id, lesson_ids=lesson_ids)
    await db.commit()
    return sorted(lessons, key=lambda lesson: lesson.position)


async def start_video_upload(
    db: AsyncSession, *, teacher: User, lesson_id: uuid.UUID, provider: VideoProvider, ip: str | None
):
    """Asks the provider for one-time upload credentials. The file itself goes client -> provider."""
    lesson = await get_own_lesson(db, teacher=teacher, lesson_id=lesson_id)
    try:
        credentials = await provider.create_upload(title=lesson.title)
    except VideoProviderError:
        raise _provider_error() from None

    await _delete_remote_video(provider, lesson)  # re-upload replaces the old video
    lesson.provider = provider.name
    lesson.provider_video_id = credentials.video_id
    lesson.status = LessonStatus.UPLOADING
    lesson.duration_seconds = None
    log_event(
        db,
        AuditEvent.VIDEO_UPLOAD_STARTED,
        user_id=teacher.id,
        ip=ip,
        lesson_id=lesson.id,
        provider=provider.name,
        provider_video_id=credentials.video_id,
    )
    await db.commit()
    return lesson, credentials


def apply_video_info(lesson: Lesson, info: VideoInfo) -> bool:
    """Returns True if something changed."""
    changed = lesson.status != info.status or lesson.duration_seconds != info.duration_seconds
    lesson.status = info.status
    lesson.duration_seconds = info.duration_seconds
    return changed


async def sync_video_status(
    db: AsyncSession,
    *,
    lesson: Lesson,
    provider: VideoProvider,
    ip: str | None,
    source: str,
    actor_id: uuid.UUID | None = None,
) -> Lesson:
    """Pulls the real status from the provider API (used by the webhook and by manual sync)."""
    if not lesson.provider_video_id or lesson.provider != provider.name:
        return lesson
    try:
        info = await provider.get_video_info(lesson.provider_video_id)
    except VideoProviderError:
        raise _provider_error() from None
    if info is None:
        info = VideoInfo(status=LessonStatus.FAILED)
    old_status = lesson.status
    if apply_video_info(lesson, info):
        log_event(
            db,
            AuditEvent.VIDEO_STATUS_UPDATED,
            user_id=actor_id,
            ip=ip,
            lesson_id=lesson.id,
            source=source,
            old_status=old_status,
            new_status=lesson.status,
        )
    await db.commit()
    return lesson
