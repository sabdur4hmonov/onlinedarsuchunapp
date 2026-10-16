"""Test setup.

Tests run against a REAL PostgreSQL database (TEST_DATABASE_URL from .env).
That database is wiped and re-created with Alembic migrations on every run,
so the migrations themselves are tested too. Never point it at real data.
"""

import asyncio
import uuid
from dataclasses import dataclass

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps import login_rate_limiter
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.models import AuditLog, Course, Enrollment, User, UserRole

PASSWORD = "Str0ng-pass!"


def _test_db_url() -> str:
    settings = get_settings()
    url = settings.test_database_url
    if not url:
        pytest.exit("TEST_DATABASE_URL .env faylida ko'rsatilmagan")
    if url == settings.database_url:
        pytest.exit("TEST_DATABASE_URL asosiy DATABASE_URL bilan bir xil bo'lmasligi kerak (testlar bazani o'chiradi!)")
    return url


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    url = _test_db_url()

    async def reset_schema():
        engine = create_async_engine(url, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await engine.dispose()

    asyncio.run(reset_schema())
    cfg = Config("alembic.ini")
    cfg.attributes["database_url"] = url
    command.upgrade(cfg, "head")


@pytest.fixture
async def session_factory():
    engine = create_async_engine(_test_db_url(), poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE audit_logs, consents, used_refresh_tokens, sessions, devices, enrollments, courses, "
                "users RESTART IDENTITY CASCADE"
            )
        )
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def db(session_factory) -> AsyncSession:
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(session_factory):
    async def _get_test_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _get_test_db
    # Most tests do many logins from one IP; the rate-limit test lowers this again
    login_rate_limiter.reset()
    login_rate_limiter.max_attempts = 1000
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    login_rate_limiter.reset()
    login_rate_limiter.max_attempts = get_settings().login_rate_limit_attempts


# ---------- helpers ----------


def new_device_id() -> str:
    return f"device-{uuid.uuid4().hex}"


@dataclass
class Tokens:
    access: str
    refresh: str
    device_id: str

    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access}", "X-Device-ID": self.device_id}


async def register_student(client: AsyncClient, phone: str) -> dict:
    r = await client.post("/auth/register", json={"phone": phone, "full_name": "Test O'quvchi", "password": PASSWORD})
    assert r.status_code == 201, r.text
    return r.json()


async def create_teacher(db: AsyncSession, phone: str = "+998900000001") -> User:
    teacher = User(phone=phone, full_name="Test O'qituvchi", password_hash=hash_password(PASSWORD), role=UserRole.TEACHER)
    db.add(teacher)
    await db.commit()
    return teacher


async def create_course_with_student(db: AsyncSession, teacher: User, student_id: str) -> Course:
    course = Course(teacher_id=teacher.id, title="Matematika")
    db.add(course)
    await db.flush()
    db.add(Enrollment(student_id=uuid.UUID(student_id), course_id=course.id))
    await db.commit()
    return course


async def login(client: AsyncClient, phone: str, device_id: str):
    return await client.post("/auth/login", json={"phone": phone, "password": PASSWORD}, headers={"X-Device-ID": device_id})


async def login_and_bind(client: AsyncClient, phone: str, device_id: str | None = None) -> Tokens:
    """Full student flow on a new device: login -> binding_required -> confirm binding."""
    device_id = device_id or new_device_id()
    r = await login(client, phone, device_id)
    assert r.status_code == 200, r.text
    body = r.json()
    if body["status"] == "device_binding_required":
        r = await client.post(
            "/auth/devices/bind",
            json={"binding_token": body["binding_token"], "device_name": "Test phone", "platform": "android"},
            headers={"X-Device-ID": device_id},
        )
        assert r.status_code == 200, r.text
        body = r.json()
    assert body["status"] == "ok"
    return Tokens(access=body["access_token"], refresh=body["refresh_token"], device_id=device_id)


async def audit_events(db: AsyncSession, event_type: str) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.event_type == event_type).execution_options(populate_existing=True)
    return list(await db.scalars(stmt))
