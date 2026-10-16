from fastapi import FastAPI

from app.api.routes import auth, consents, courses, teacher

app = FastAPI(title="Online Dars — backend", version="0.1.0")

app.include_router(auth.router)
app.include_router(consents.router)
app.include_router(courses.router)
app.include_router(teacher.router)


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok"}
