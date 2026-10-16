"""Admin commands.

Create a teacher account (password is asked interactively, it is not shown on screen):
    python -m app.cli create-teacher --phone +998901234567 --name "Ali Valiyev"
"""

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select

from app.core.phone import normalize_phone
from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.models import User, UserRole


async def create_teacher(phone: str, full_name: str, password: str) -> None:
    async with SessionLocal() as db:
        if await db.scalar(select(User).where(User.phone == phone)):
            sys.exit(f"Xato: {phone} raqami bilan foydalanuvchi allaqachon bor")
        db.add(User(phone=phone, full_name=full_name, password_hash=hash_password(password), role=UserRole.TEACHER))
        await db.commit()
    await engine.dispose()
    print(f"O'qituvchi yaratildi: {full_name} ({phone})")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    teacher = sub.add_parser("create-teacher", help="O'qituvchi akkaunti yaratish")
    teacher.add_argument("--phone", required=True)
    teacher.add_argument("--name", required=True)
    args = parser.parse_args()

    if args.command == "create-teacher":
        try:
            phone = normalize_phone(args.phone)
        except ValueError as e:
            sys.exit(f"Xato: {e}")
        password = getpass.getpass("Parol (kamida 8 belgi): ")
        if len(password) < 8 or password != getpass.getpass("Parolni takrorlang: "):
            sys.exit("Xato: parol juda qisqa yoki mos kelmadi")
        asyncio.run(create_teacher(phone, args.name, password))


if __name__ == "__main__":
    main()
