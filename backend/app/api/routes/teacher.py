import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import ClientIp, DbSession, TeacherAuth
from app.core.errors import api_error
from app.models import Course, Device, Enrollment, EnrollmentStatus, User, UserRole
from app.schemas.course import (
    AuditActorOut,
    AuditEventOut,
    CourseCreate,
    CourseOut,
    CourseStudentOut,
    CourseUpdate,
    DeviceOut,
    DeviceResetRequest,
    DeviceResetResponse,
    EnrollmentOut,
    EnrollRequest,
)
from app.services import course_events, device_service, lesson_service, teacher_service
from app.services.audit import AuditEvent, log_event

router = APIRouter(prefix="/teacher", tags=["teacher"])


@router.post("/courses", response_model=CourseOut, status_code=201)
async def create_course(body: CourseCreate, auth: TeacherAuth, db: DbSession, ip: ClientIp):
    course = Course(teacher_id=auth.user.id, title=body.title, description=body.description)
    db.add(course)
    await db.flush()
    log_event(db, AuditEvent.COURSE_CREATED, user_id=auth.user.id, ip=ip, course_id=course.id)
    await db.commit()
    await db.refresh(course)
    return course


@router.get("/courses", response_model=list[CourseOut])
async def my_courses(auth: TeacherAuth, db: DbSession):
    return list(await db.scalars(select(Course).where(Course.teacher_id == auth.user.id).order_by(Course.created_at)))


@router.get("/courses/{course_id}", response_model=CourseOut)
async def get_course(course_id: uuid.UUID, auth: TeacherAuth, db: DbSession):
    return await lesson_service.get_own_course(db, teacher=auth.user, course_id=course_id)


@router.patch("/courses/{course_id}", response_model=CourseOut)
async def update_course(course_id: uuid.UUID, body: CourseUpdate, auth: TeacherAuth, db: DbSession, ip: ClientIp):
    course = await lesson_service.get_own_course(db, teacher=auth.user, course_id=course_id)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("title", "") is None:
        raise api_error(422, "title_required", "Kurs nomi bo'sh bo'lishi mumkin emas")
    for field, value in changes.items():
        setattr(course, field, value)
    log_event(db, AuditEvent.COURSE_UPDATED, user_id=auth.user.id, ip=ip, course_id=course.id, fields=sorted(changes))
    await db.commit()
    await db.refresh(course)
    return course


@router.get("/courses/{course_id}/students", response_model=list[CourseStudentOut])
async def course_students(course_id: uuid.UUID, auth: TeacherAuth, db: DbSession):
    """Active students of the course with the number of their bound devices."""
    course = await lesson_service.get_own_course(db, teacher=auth.user, course_id=course_id)
    active_devices = (
        select(func.count())
        .select_from(Device)
        .where(Device.user_id == User.id, Device.is_active.is_(True))
        .scalar_subquery()
    )
    rows = await db.execute(
        select(User, Enrollment.status, active_devices)
        .join(Enrollment, Enrollment.student_id == User.id)
        .where(Enrollment.course_id == course.id, Enrollment.status == EnrollmentStatus.ACTIVE)
        .order_by(User.full_name)
    )
    return [
        CourseStudentOut(
            id=user.id, full_name=user.full_name, phone=user.phone, enrollment_status=status, active_devices=devices
        )
        for user, status, devices in rows.all()
    ]


@router.delete("/courses/{course_id}/students/{student_id}", status_code=204)
async def remove_student(course_id: uuid.UUID, student_id: uuid.UUID, auth: TeacherAuth, db: DbSession, ip: ClientIp):
    """Removes the student from the course (enrollment is kept as `suspended` for history)."""
    course = await lesson_service.get_own_course(db, teacher=auth.user, course_id=course_id)
    enrollment = await db.get(Enrollment, (student_id, course.id))
    if enrollment is None or enrollment.status != EnrollmentStatus.ACTIVE:
        raise api_error(404, "student_not_found", "O'quvchi bu kursda topilmadi")
    enrollment.status = EnrollmentStatus.SUSPENDED
    log_event(db, AuditEvent.STUDENT_REMOVED, user_id=auth.user.id, ip=ip, course_id=course.id, student_id=student_id)
    await db.commit()


@router.get("/courses/{course_id}/events", response_model=list[AuditEventOut])
async def course_events_journal(
    course_id: uuid.UUID,
    auth: TeacherAuth,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before_id: Annotated[int | None, Query()] = None,
    event_type: Annotated[list[str] | None, Query()] = None,
):
    """Security journal of the course, newest first. Paginate with `before_id` = last `id` seen."""
    course = await lesson_service.get_own_course(db, teacher=auth.user, course_id=course_id)
    rows = await course_events.list_course_events(
        db, course.id, limit=limit, before_id=before_id, event_types=event_type
    )
    return [
        AuditEventOut(
            id=log.id,
            event_type=log.event_type,
            created_at=log.created_at,
            ip=log.ip,
            actor=AuditActorOut(id=user.id, full_name=user.full_name, phone=user.phone, role=user.role.value)
            if user
            else None,
            details=log.details or {},
        )
        for log, user in rows
    ]


@router.post("/courses/{course_id}/enrollments", response_model=EnrollmentOut, status_code=201)
async def enroll_student(course_id: uuid.UUID, body: EnrollRequest, auth: TeacherAuth, db: DbSession, ip: ClientIp):
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
    log_event(db, AuditEvent.STUDENT_ENROLLED, user_id=auth.user.id, ip=ip, course_id=course.id, student_id=student.id)
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
