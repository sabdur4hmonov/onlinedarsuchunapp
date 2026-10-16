import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course, Device, Enrollment, User
from app.services.audit import AuditEvent, log_event
from app.services.session_service import revoke_sessions


async def teacher_owns_student(db: AsyncSession, *, teacher_id: uuid.UUID, student_id: uuid.UUID) -> bool:
    """True if the student is enrolled in at least one course of this teacher."""
    found = await db.scalar(
        select(Enrollment.student_id)
        .join(Course, Course.id == Enrollment.course_id)
        .where(Enrollment.student_id == student_id, Course.teacher_id == teacher_id)
        .limit(1)
    )
    return found is not None


async def reset_devices(
    db: AsyncSession, *, teacher: User, student: User, device_pk: uuid.UUID | None, ip: str | None
) -> list[Device]:
    """Unbinds one device (or all of them) and kills their sessions. Caller commits.

    Permission (teacher owns one of the student's courses) is checked by the caller.
    """
    stmt = select(Device).where(Device.user_id == student.id, Device.is_active.is_(True))
    if device_pk is not None:
        stmt = stmt.where(Device.id == device_pk)
    devices = list(await db.scalars(stmt.with_for_update()))
    for device in devices:
        device.is_active = False

    if devices:
        await revoke_sessions(
            db,
            user_id=student.id,
            reason="device_reset",
            ip=ip,
            device_ids=[d.device_id for d in devices],
            actor_id=teacher.id,
        )
    log_event(
        db,
        AuditEvent.DEVICE_RESET,
        user_id=teacher.id,
        ip=ip,
        student_id=student.id,
        device_ids=[d.device_id for d in devices],
        requested_device_pk=device_pk,
    )
    return devices
