from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, consents, courses, dev, lessons, live, teacher, teacher_lessons, teacher_live, webhooks
from app.core.config import get_settings
from app.services.live import get_live_provider
from app.services.storage import get_recording_storage
from app.services.video import get_video_provider


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Fail at startup (not on the first student request) if the video setup is unsafe
    get_video_provider()
    get_live_provider()
    get_recording_storage()
    yield


app = FastAPI(title="Online Dars — backend", version="0.4.0", lifespan=lifespan)

class SettingsCORSMiddleware(CORSMiddleware):
    """Only origins listed in CORS_ALLOWED_ORIGINS (e.g. the teacher panel) may call the API
    from a browser; everything else gets no CORS headers. The API uses no cookies, so
    credentials stay off."""

    def is_allowed_origin(self, origin: str) -> bool:
        return origin in get_settings().cors_origins


app.add_middleware(
    SettingsCORSMiddleware,
    allow_origins=[],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Device-ID"],
    max_age=600,
)

app.include_router(auth.router)
app.include_router(consents.router)
app.include_router(courses.router)
app.include_router(lessons.router)
app.include_router(live.router)
app.include_router(teacher.router)
app.include_router(teacher_lessons.router)
app.include_router(teacher_live.router)
app.include_router(webhooks.router)
app.include_router(dev.router)


@app.get("/health", tags=["system"])
async def health():
    return {
        "status": "ok",
        "video_provider": get_video_provider().name,
        "live_provider": get_live_provider().name,
        "recording_storage": get_recording_storage().name,
    }
