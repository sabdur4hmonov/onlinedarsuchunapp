import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, str_enum


class LiveSessionStatus(enum.StrEnum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    ENDED = "ended"
    CANCELLED = "cancelled"


class RecordingStatus(enum.StrEnum):
    NONE = "none"  # not started yet
    RECORDING = "recording"  # egress is writing the mp4
    UPLOADING = "uploading"  # egress finishing the file / file being handed to the video provider
    PROCESSING = "processing"  # video provider is encoding it
    READY = "ready"  # lesson is playable AND the raw mp4 was deleted from temporary storage
    FAILED = "failed"  # see recording_error + audit_logs; teacher can retry


class LiveSession(Base):
    __tablename__ = "live_sessions"
    __table_args__ = (Index("ix_live_sessions_course_id_scheduled_at", "course_id", "scheduled_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[LiveSessionStatus] = mapped_column(
        str_enum(LiveSessionStatus, "live_session_status", 16), default=LiveSessionStatus.SCHEDULED
    )
    # Random, unguessable LiveKit room name (never derived from IDs or titles)
    room_name: Mapped[str] = mapped_column(String(64), unique=True)
    egress_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    recording_status: Mapped[RecordingStatus] = mapped_column(
        str_enum(RecordingStatus, "recording_status", 16), default=RecordingStatus.NONE
    )
    # Where egress writes the mp4 in the temporary bucket; cleared once the file is deleted
    recording_object_key: Mapped[str | None] = mapped_column(String(512))
    # Short reason of the last recording failure ("step: reason"); details are in audit_logs
    recording_error: Mapped[str | None] = mapped_column(String(512))
    resulting_lesson_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("lessons.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
