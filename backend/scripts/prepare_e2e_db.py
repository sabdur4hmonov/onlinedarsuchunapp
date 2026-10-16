"""Prepares a throwaway database for the teacher panel's Playwright tests.

    DATABASE_URL=postgresql+asyncpg://.../course_platform_e2e python scripts/prepare_e2e_db.py

Creates the database if needed, wipes it, applies all migrations and seeds the demo
accounts (see seed_demo.py). Refuses to touch a database whose name does not end in "_e2e".
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import asyncpg

BACKEND = Path(__file__).resolve().parents[1]


async def recreate(url: str) -> None:
    dsn = url.replace("postgresql+asyncpg://", "postgresql://")
    base, db_name = dsn.rsplit("/", 1)
    if not db_name.endswith("_e2e"):
        sys.exit(f"Refusing to wipe '{db_name}': E2E database names must end with _e2e")
    admin = await asyncpg.connect(f"{base}/postgres")
    try:
        if not await admin.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db_name):
            await admin.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await admin.close()
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    finally:
        await conn.close()


def main() -> None:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        sys.exit("Set DATABASE_URL to the E2E database")
    asyncio.run(recreate(url))
    python = sys.executable
    subprocess.run([python, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True)
    subprocess.run([python, "scripts/seed_demo.py"], cwd=BACKEND, check=True)
    print("E2E database ready")


if __name__ == "__main__":
    main()
