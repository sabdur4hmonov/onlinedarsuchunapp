import uuid
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from app.models import LiveSessionStatus, RecordingStatus


class LiveSessionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    # With timezone, e.g. "2026-10-20T15:00:00+05:00"
    scheduled_at: AwareDatetime


class LiveSessionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    scheduled_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def _not_empty(self):
        if not self.model_fields_set:
            raise ValueError("Kamida bitta maydonni yuboring: title yoki scheduled_at")
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} bo'sh bo'lishi mumkin emas")
        return self


class LiveSessionOut(BaseModel):
    """Teacher view. The room name is deliberately not exposed."""

    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    scheduled_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    status: LiveSessionStatus
    recording_status: RecordingStatus
    recording_error: str | None
    resulting_lesson_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class LiveSessionPublicOut(BaseModel):
    """Student view."""

    id: uuid.UUID
    title: str
    scheduled_at: datetime
    started_at: datetime | None
    status: LiveSessionStatus

    model_config = {"from_attributes": True}


class ClientOptions(BaseModel):
    """Pass these to the LiveKit client SDK (Room options / publish options)."""

    adaptive_stream: bool
    dynacast: bool
    simulcast: bool
    auto_subscribe: bool


class TeacherLiveTokenOut(BaseModel):
    live_session: LiveSessionOut
    url: str
    token: str
    expires_in: int
    client_options: ClientOptions


class WatermarkOut(BaseModel):
    """The app must draw this over the video (semi-transparent, moving every few seconds)."""

    user_id: uuid.UUID
    phone: str
    text: str


class StudentJoinOut(BaseModel):
    live_session: LiveSessionPublicOut
    url: str
    token: str  # subscribe-only
    expires_in: int  # only for JOINING; an established connection is kept alive by LiveKit
    identity: str
    watermark: WatermarkOut
    client_options: ClientOptions
