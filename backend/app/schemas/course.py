import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.phone import normalize_phone
from app.models import ConsentType, EnrollmentStatus
from app.schemas.lesson import LessonPublicOut


class CourseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None


class CourseOut(BaseModel):
    id: uuid.UUID
    teacher_id: uuid.UUID
    title: str
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class EnrollRequest(BaseModel):
    student_phone: str

    @field_validator("student_phone")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return normalize_phone(v)


class EnrollmentOut(BaseModel):
    student_id: uuid.UUID
    course_id: uuid.UUID
    status: EnrollmentStatus

    model_config = {"from_attributes": True}


class CourseContentOut(BaseModel):
    course: CourseOut
    # Only lessons whose video is ready. Play one with POST /lessons/{id}/playback
    lessons: list[LessonPublicOut] = []


class DeviceOut(BaseModel):
    id: uuid.UUID
    device_id: str
    device_name: str
    platform: str
    bound_at: datetime
    is_active: bool

    model_config = {"from_attributes": True}


class DeviceResetRequest(BaseModel):
    # devices.id of one device; leave empty to reset ALL devices of the student
    device_id: uuid.UUID | None = None


class DeviceResetResponse(BaseModel):
    reset_devices: list[DeviceOut]


class ConsentCreate(BaseModel):
    type: ConsentType


class ConsentOut(BaseModel):
    type: ConsentType
    version: str
    granted_at: datetime

    model_config = {"from_attributes": True}
