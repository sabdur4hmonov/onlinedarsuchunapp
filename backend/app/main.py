from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import auth, consents, courses, lessons, teacher, teacher_lessons, webhooks
from app.services.video import get_video_provider


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Fail at startup (not on the first student request) if the video setup is unsafe
    get_video_provider()
    yield


app = FastAPI(title="Online Dars — backend", version="0.2.0", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(consents.router)
app.include_router(courses.router)
app.include_router(lessons.router)
app.include_router(teacher.router)
app.include_router(teacher_lessons.router)
app.include_router(webhooks.router)


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "video_provider": get_video_provider().name}
