"""Creates demo accounts for local testing and the panel's Playwright tests.

    python scripts/seed_demo.py            # uses DATABASE_URL from .env
    python scripts/seed_demo.py --reset    # first DELETES all data (refuses outside development)

Accounts (test-only passwords, never use them anywhere real):
    teacher  +998900000001 / Demo-Teacher-1
    teacher  +998900000002 / Demo-Teacher-2   (owns nothing; for permission tests)
    student  +998901000001 / Demo-Student-1
    student  +998901000002 / Demo-Student-2
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models import User, UserRole  # noqa: E402

ACCOUNTS = [
    ("+998900000001", "Demo O'qituvchi", "Demo-Teacher-1", UserRole.TEACHER),
    ("+998900000002", "Boshqa O'qituvchi", "Demo-Teacher-2", UserRole.TEACHER),
    ("+998901000001", "Ali Valiyev", "Demo-Student-1", UserRole.STUDENT),
    ("+998901000002", "Malika Karimova", "Demo-Student-2", UserRole.STUDENT),
]

TABLES = (
    "audit_logs, consents, used_refresh_tokens, sessions, devices, live_sessions, lessons, "
    "enrollments, courses, users"
)


async def main(reset: bool) -> None:
    settings = get_settings()
    async with SessionLocal() as db:
        if reset:
            if settings.environment == "production":
                sys.exit("Refusing to wipe data in production")
            await db.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
        for phone, name, password, role in ACCOUNTS:
            if await db.scalar(select(User.id).where(User.phone == phone)):
                continue
            db.add(User(phone=phone, full_name=name, password_hash=hash_password(password), role=role))
        await db.commit()
    await engine.dispose()
    print("demo accounts ready")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    asyncio.run(main(parser.parse_args().reset))
