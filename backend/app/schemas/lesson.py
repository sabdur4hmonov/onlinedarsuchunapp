import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models import LessonStatus


class LessonCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None


class LessonUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None

    @model_validator(mode="after")
    def _not_empty(self):
        if not self.model_fields_set:
            raise ValueError("Kamida bitta maydonni yuboring: title yoki description")
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title bo'sh bo'lishi mumkin emas")
        return self


class LessonReorder(BaseModel):
    # ALL lesson IDs of the course in the new order
    lesson_ids: list[uuid.UUID] = Field(min_length=1)


class LessonOut(BaseModel):
    """Teacher view: includes video status."""

    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    description: str | None
    position: int
    provider: str | None
    provider_video_id: str | None
    status: LessonStatus
    duration_seconds: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class LessonPublicOut(BaseModel):
    """Student view: no provider internals."""

    id: uuid.UUID
    title: str
    description: str | None
    position: int
    duration_seconds: int | None

    model_config = {"from_attributes": True}


class VideoUploadOut(BaseModel):
    """Upload the file DIRECTLY to `upload_url` (multipart POST): all `fields` first, then the file as "file"."""

    lesson: LessonOut
    upload_url: str
    fields: dict[str, str]


class PlaybackOut(BaseModel):
    """Pass `otp` + `playback_info` to the VdoCipher Flutter player. Valid for `expires_in` seconds."""

    provider: str
    otp: str
    playback_info: str
    expires_in: int
