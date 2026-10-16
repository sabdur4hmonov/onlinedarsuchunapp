import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, str_enum


class UserRole(enum.StrEnum):
    TEACHER = "teacher"
    STUDENT = "student"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Always stored normalized: +998XXXXXXXXX (see app/core/phone.py)
    phone: Mapped[str] = mapped_column(String(16), unique=True)
    full_name: Mapped[str] = mapped_column(String(255))
    # Nullable on purpose: once SMS OTP login exists, a user may have no password at all
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(str_enum(UserRole, "user_role", 16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
