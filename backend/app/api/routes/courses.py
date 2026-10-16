import uuid

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import ContentAuth, DbSession, StudentAuth
from app.core.errors import api_error
from app.models import Course, Enrollment, EnrollmentStatus
from app.schemas.course import CourseContentOut, CourseOut
from app.schemas.lesson import LessonPublicOut
from app.services import lesson_service

router = APIRouter(prefix="/courses", tags=["student courses"])


@router.get("/my", response_model=list[CourseOut])
async def my_courses(auth: StudentAuth, db: DbSession):
    """List of courses only (no content) — available even before consent."""
    return list(
        await db.scalars(
            select(Course)
            .join(Enrollment, Enrollment.course_id == Course.id)
            .where(Enrollment.student_id == auth.user.id, Enrollment.status == EnrollmentStatus.ACTIVE)
            .order_by(Course.created_at)
        )
    )


@router.get("/{course_id}/content", response_model=CourseContentOut)
async def course_content(course_id: uuid.UUID, auth: ContentAuth, db: DbSession):
    """Protected content: requires camera + data_processing consent (else 403 consent_required)."""
    course = await db.scalar(
        select(Course)
        .join(Enrollment, Enrollment.course_id == Course.id)
        .where(
            Course.id == course_id,
            Enrollment.student_id == auth.user.id,
            Enrollment.status == EnrollmentStatus.ACTIVE,
        )
    )
    if course is None:
        raise api_error(404, "course_not_found", "Kurs topilmadi yoki siz unga yozilmagansiz")
    lessons = await lesson_service.list_lessons(db, course.id, only_ready=True)
    return CourseContentOut(
        course=CourseOut.model_validate(course), lessons=[LessonPublicOut.model_validate(x) for x in lessons]
    )
