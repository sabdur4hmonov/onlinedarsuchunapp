from fastapi import APIRouter

from app.api.deps import Auth, ClientIp, DbSession, DeviceId, login_rate_limiter
from app.core.errors import api_error
from app.schemas.auth import (
    BindDeviceRequest,
    DeviceBindingRequiredResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.services import auth_service, session_service
from app.services.audit import AuditEvent, log_event

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
async def register(body: RegisterRequest, db: DbSession, ip: ClientIp):
    """Student self-registration. Teachers are created with `python -m app.cli create-teacher`.

    TODO (SMS OTP stage): confirm phone ownership with a code before creating the account.
    """
    if not await login_rate_limiter.hit(f"register-ip:{ip}"):
        raise api_error(429, "too_many_attempts", "Juda ko'p urinish. Bir daqiqadan keyin qayta urinib ko'ring")
    return await auth_service.register_student(
        db, phone=body.phone, full_name=body.full_name, password=body.password, ip=ip
    )


@router.post("/login", response_model=TokenResponse | DeviceBindingRequiredResponse)
async def login(body: LoginRequest, db: DbSession, ip: ClientIp, device_id: DeviceId):
    """Returns either tokens (`status: ok`) or `status: device_binding_required`."""
    if not await login_rate_limiter.hit(f"login-ip:{ip}", f"login-phone:{body.phone}"):
        log_event(db, AuditEvent.LOGIN_RATE_LIMITED, ip=ip, phone=body.phone, device_id=device_id)
        await db.commit()
        raise api_error(429, "too_many_attempts", "Juda ko'p urinish. Bir daqiqadan keyin qayta urinib ko'ring")
    return await auth_service.login_with_password(
        db, phone=body.phone, password=body.password, device_id=device_id, ip=ip
    )


@router.post("/devices/bind", response_model=TokenResponse)
async def bind_device(body: BindDeviceRequest, db: DbSession, ip: ClientIp, device_id: DeviceId):
    """Student confirmed "bind this device" in the app. Binds it and finishes the login."""
    return await auth_service.confirm_device_binding(
        db,
        binding_token=body.binding_token,
        device_id=device_id,
        device_name=body.device_name,
        platform=body.platform,
        ip=ip,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: DbSession, ip: ClientIp, device_id: DeviceId):
    """Rotation: the sent refresh token becomes invalid, use the new one from the response."""
    return await session_service.refresh(db, refresh_token=body.refresh_token, device_id=device_id, ip=ip)


@router.post("/logout", status_code=204)
async def logout(auth: Auth, db: DbSession, ip: ClientIp):
    await session_service.revoke_sessions(
        db, user_id=auth.user.id, reason="logout", ip=ip, session_id=auth.session.id
    )
    log_event(db, AuditEvent.LOGOUT, user_id=auth.user.id, ip=ip, session_id=auth.session.id)
    await db.commit()


@router.get("/me", response_model=UserOut)
async def me(auth: Auth):
    return auth.user
