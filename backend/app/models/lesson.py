import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, str_enum


class LessonStatus(enum.StrEnum):
    UPLOADING = "uploading"  # lesson created / waiting for the video file
    PROCESSING = "processing"  # file received, provider is encoding it
    READY = "ready"  # can be played
    FAILED = "failed"


class Lesson(Base):
    __tablename__ = "lessons"
    __table_args__ = (
        Index("ix_lessons_course_id_position", "course_id", "position"),
        # Webhooks find the lesson by the provider's video ID
        UniqueConstraint("provider", "provider_video_id", name="uq_lessons_provider_provider_video_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    # Order inside the course: 1, 2, 3, ...
    position: Mapped[int] = mapped_column(Integer)
    # e.g. "vdocipher" or "mock"; empty until a video upload is started
    provider: Mapped[str | None] = mapped_column(String(32))
    provider_video_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[LessonStatus] = mapped_column(str_enum(LessonStatus, "lesson_status", 16), default=LessonStatus.UPLOADING)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
