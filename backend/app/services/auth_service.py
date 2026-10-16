"""Login flow.

Step 1 — prove identity. Today: phone + password (`login_with_password`).
         Later: phone + SMS OTP — add `login_with_otp` that verifies the code and then
         calls the same `continue_login`. Device and session rules live only in step 2.
Step 2 — `continue_login`: device rules + single active session.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import api_error
from app.core.security import (
    DEVICE_BINDING_TOKEN_TYPE,
    create_device_binding_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import User, UserRole
from app.schemas.auth import DeviceBindingRequiredResponse, TokenResponse
from app.services import device_service, session_service
from app.services.audit import AuditEvent, log_event


def _device_limit_error(max_devices: int):
    return api_error(
        403,
        "device_limit_reached",
        f"Bu akkauntga {max_devices} ta qurilma bog'langan. Yangi qurilmadan kirish uchun o'qituvchingizga murojaat qiling.",
        max_devices=max_devices,
    )


async def register_student(db: AsyncSession, *, phone: str, full_name: str, password: str, ip: str | None) -> User:
    user = User(id=uuid.uuid4(), phone=phone, full_name=full_name, password_hash=hash_password(password), role=UserRole.STUDENT)
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise api_error(409, "phone_taken", "Bu telefon raqam allaqachon ro'yxatdan o'tgan") from None
    log_event(db, AuditEvent.USER_REGISTERED, user_id=user.id, ip=ip, role=user.role)
    await db.commit()
    return user


async def login_with_password(
    db: AsyncSession, *, phone: str, password: str, device_id: str, ip: str | None
) -> TokenResponse | DeviceBindingRequiredResponse:
    user = await db.scalar(select(User).where(User.phone == phone))
    if not verify_password(password, user.password_hash if user else None):
        log_event(db, AuditEvent.LOGIN_FAILED, user_id=user.id if user else None, ip=ip, phone=phone, device_id=device_id)
        await db.commit()
        # Same message for "no such user" and "wrong password"
        raise api_error(401, "invalid_credentials", "Telefon raqam yoki parol noto'g'ri")
    return await continue_login(db, user=user, device_id=device_id, ip=ip)


async def continue_login(
    db: AsyncSession, *, user: User, device_id: str, ip: str | None
) -> TokenResponse | DeviceBindingRequiredResponse:
    """Identity is already proven. Applies device rules and opens a session."""
    settings = get_settings()

    # Rule 6: teachers have no device restrictions
    if user.role == UserRole.TEACHER:
        return await session_service.open_session(db, user=user, device_id=device_id, ip=ip)

    if await device_service.get_active_device(db, user.id, device_id):
        return await session_service.open_session(db, user=user, device_id=device_id, ip=ip)

    # Unknown device. Rule 2: with the limit reached, login is refused outright.
    bound = await device_service.count_active_devices(db, user.id)
    if bound >= settings.max_student_devices:
        log_event(
            db, AuditEvent.LOGIN_DENIED, user_id=user.id, ip=ip, reason="device_limit_reached", device_id=device_id
        )
        await db.commit()
        raise _device_limit_error(settings.max_student_devices)

    # Rule 1: never bind automatically — the student must confirm in the app first
    log_event(db, AuditEvent.DEVICE_BINDING_REQUIRED, user_id=user.id, ip=ip, device_id=device_id)
    await db.commit()
    return DeviceBindingRequiredResponse(
        binding_token=create_device_binding_token(user_id=user.id, device_id=device_id),
        max_devices=settings.max_student_devices,
        bound_devices=bound,
        message=(
            f"Bu akkauntga faqat {settings.max_student_devices} ta qurilma bog'lay olasiz "
            f"(hozir {bound} ta bog'langan). Bu qurilmani bog'laysizmi?"
        ),
    )


async def confirm_device_binding(
    db: AsyncSession, *, binding_token: str, device_id: str, device_name: str, platform: str, ip: str | None
) -> TokenResponse:
    """Called after the student pressed "Ha" — binds the device and finishes the login."""
    settings = get_settings()
    payload = decode_token(binding_token, DEVICE_BINDING_TOKEN_TYPE)
    if payload is None or payload.get("did") != device_id:
        raise api_error(401, "invalid_binding_token", "Tasdiqlash muddati o'tgan, qaytadan kiring")

    # Lock the user row: two parallel bind requests must not both slip under the limit
    user = await db.scalar(select(User).where(User.id == uuid.UUID(payload["sub"])).with_for_update())
    if user is None or user.role != UserRole.STUDENT:
        raise api_error(401, "invalid_binding_token", "Tasdiqlash muddati o'tgan, qaytadan kiring")

    if not await device_service.get_active_device(db, user.id, device_id):
        if await device_service.count_active_devices(db, user.id) >= settings.max_student_devices:
            log_event(
                db, AuditEvent.LOGIN_DENIED, user_id=user.id, ip=ip, reason="device_limit_reached", device_id=device_id
            )
            await db.commit()
            raise _device_limit_error(settings.max_student_devices)
        await device_service.bind_device(
            db, user=user, device_id=device_id, device_name=device_name, platform=platform, ip=ip
        )
    return await session_service.open_session(db, user=user, device_id=device_id, ip=ip)
