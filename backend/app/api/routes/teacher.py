import uuid

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import ClientIp, DbSession, TeacherAuth
from app.core.errors import api_error
from app.models import Course, Enrollment, EnrollmentStatus, User, UserRole
from app.schemas.course import (
    CourseCreate,
    CourseOut,
    DeviceOut,
    DeviceResetRequest,
    DeviceResetResponse,
    EnrollmentOut,
    EnrollRequest,
)
from app.services import device_service, teacher_service

router = APIRouter(prefix="/teacher", tags=["teacher"])


@router.post("/courses", response_model=CourseOut, status_code=201)
async def create_course(body: CourseCreate, auth: TeacherAuth, db: DbSession):
    course = Course(teacher_id=auth.user.id, title=body.title, description=body.description)
    db.add(course)
    await db.commit()
    await db.refresh(course)
    return course


@router.get("/courses", response_model=list[CourseOut])
async def my_courses(auth: TeacherAuth, db: DbSession):
    return list(await db.scalars(select(Course).where(Course.teacher_id == auth.user.id).order_by(Course.created_at)))


@router.post("/courses/{course_id}/enrollments", response_model=EnrollmentOut, status_code=201)
async def enroll_student(course_id: uuid.UUID, body: EnrollRequest, auth: TeacherAuth, db: DbSession):
    course = await db.get(Course, course_id)
    if course is None or course.teacher_id != auth.user.id:
        raise api_error(404, "course_not_found", "Kurs topilmadi")
    student = await db.scalar(select(User).where(User.phone == body.student_phone, User.role == UserRole.STUDENT))
    if student is None:
        raise api_error(404, "student_not_found", "Bu raqam bilan o'quvchi topilmadi")

    enrollment = await db.get(Enrollment, (student.id, course.id))
    if enrollment is None:
        enrollment = Enrollment(student_id=student.id, course_id=course.id, status=EnrollmentStatus.ACTIVE)
        db.add(enrollment)
    else:
        enrollment.status = EnrollmentStatus.ACTIVE
    await db.commit()
    return enrollment


async def _get_own_student(db: DbSession, teacher_id: uuid.UUID, student_id: uuid.UUID) -> User:
    """Rule 3: a teacher manages only students enrolled in one of their own courses."""
    student = await db.get(User, student_id)
    if (
        student is None
        or student.role != UserRole.STUDENT
        or not await teacher_service.teacher_owns_student(db, teacher_id=teacher_id, student_id=student_id)
    ):
        # 404 instead of 403: do not reveal that someone else's student exists
        raise api_error(404, "student_not_found", "O'quvchi sizning kurslaringizda topilmadi")
    return student


@router.get("/students/{student_id}/devices", response_model=list[DeviceOut])
async def student_devices(student_id: uuid.UUID, auth: TeacherAuth, db: DbSession):
    student = await _get_own_student(db, auth.user.id, student_id)
    return await device_service.list_devices(db, student.id)


@router.post("/students/{student_id}/devices/reset", response_model=DeviceResetResponse)
async def reset_student_devices(
    student_id: uuid.UUID, body: DeviceResetRequest, auth: TeacherAuth, db: DbSession, ip: ClientIp
):
    """Unbinds the student's device(s) and logs them out there. Written to audit_logs."""
    student = await _get_own_student(db, auth.user.id, student_id)
    devices = await teacher_service.reset_devices(db, teacher=auth.user, student=student, device_pk=body.device_id, ip=ip)
    if body.device_id is not None and not devices:
        await db.rollback()
        raise api_error(404, "device_not_found", "Bunday faol qurilma topilmadi")
    await db.commit()
    return DeviceResetResponse(reset_devices=[DeviceOut.model_validate(d) for d in devices])
