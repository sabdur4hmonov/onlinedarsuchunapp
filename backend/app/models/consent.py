import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, str_enum


class ConsentType(enum.StrEnum):
    CAMERA = "camera"
    DATA_PROCESSING = "data_processing"
    # For students under 18 — not enforced yet, will be used in a later stage
    PARENT_CONSENT = "parent_consent"


class Consent(Base):
    __tablename__ = "consents"
    __table_args__ = (UniqueConstraint("user_id", "type", "version", name="uq_consents_user_id_type_version"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[ConsentType] = mapped_column(str_enum(ConsentType, "consent_type", 32))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Version of the consent text the user agreed to
    version: Mapped[str] = mapped_column(String(20))
