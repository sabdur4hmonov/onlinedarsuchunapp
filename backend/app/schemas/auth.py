import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.phone import normalize_phone
from app.models import UserRole


class PhoneMixin(BaseModel):
    phone: str

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, v: str) -> str:
        return normalize_phone(v)


class RegisterRequest(PhoneMixin):
    full_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(PhoneMixin):
    # Later an SMS OTP login will add a second request type (phone + code)
    # and reuse the same device/session logic in app/services/auth_service.py
    password: str = Field(min_length=1, max_length=128)


class BindDeviceRequest(BaseModel):
    binding_token: str
    device_name: str = Field(min_length=1, max_length=255)
    platform: Literal["android", "ios", "web", "other"]


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    status: Literal["ok"] = "ok"
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int  # access token lifetime, seconds


class DeviceBindingRequiredResponse(BaseModel):
    """Returned by /auth/login when this device is not bound yet.

    The app shows: "Bu akkauntga faqat 2 ta qurilma bog'lay olasiz, bu qurilmani bog'laysizmi?"
    and on "Ha" calls POST /auth/devices/bind with `binding_token`.
    """

    status: Literal["device_binding_required"] = "device_binding_required"
    binding_token: str
    max_devices: int
    bound_devices: int
    message: str


class UserOut(BaseModel):
    id: uuid.UUID
    phone: str
    full_name: str
    role: UserRole

    model_config = {"from_attributes": True}
