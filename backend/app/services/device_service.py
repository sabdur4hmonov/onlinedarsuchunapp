import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, User
from app.services.audit import AuditEvent, log_event


async def get_active_device(db: AsyncSession, user_id: uuid.UUID, device_id: str) -> Device | None:
    return await db.scalar(
        select(Device).where(Device.user_id == user_id, Device.device_id == device_id, Device.is_active.is_(True))
    )


async def count_active_devices(db: AsyncSession, user_id: uuid.UUID) -> int:
    return await db.scalar(
        select(func.count()).select_from(Device).where(Device.user_id == user_id, Device.is_active.is_(True))
    )


async def bind_device(
    db: AsyncSession, *, user: User, device_id: str, device_name: str, platform: str, ip: str | None
) -> Device:
    """Binds the device to the student. Caller must hold a lock on the user row and check the limit."""
    device = await db.scalar(select(Device).where(Device.user_id == user.id, Device.device_id == device_id))
    if device is None:
        device = Device(user_id=user.id, device_id=device_id, device_name=device_name, platform=platform)
        db.add(device)
    else:
        # Device was bound before and later reset by a teacher -> bind it again
        device.is_active = True
        device.device_name = device_name
        device.platform = platform
        device.bound_at = datetime.now(UTC)
    await db.flush()
    log_event(
        db, AuditEvent.DEVICE_BOUND, user_id=user.id, ip=ip, device_id=device_id, device_name=device_name, platform=platform
    )
    return device


async def list_devices(db: AsyncSession, user_id: uuid.UUID) -> list[Device]:
    return list(await db.scalars(select(Device).where(Device.user_id == user_id).order_by(Device.bound_at)))
