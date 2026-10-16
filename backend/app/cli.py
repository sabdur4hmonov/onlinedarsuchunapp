"""Admin commands.

Create a teacher account (password is asked interactively, it is not shown on screen):
    python -m app.cli create-teacher --phone +998901234567 --name "Ali Valiyev"

Create the private bucket for raw live recordings:
    python -m app.cli init-recordings-bucket
"""

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select

from app.core.config import get_settings
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


def init_recordings_bucket(expire_days: int) -> None:
    """Creates the PRIVATE bucket for raw recordings (MinIO locally, S3 in production).

    Safety net: a lifecycle rule deletes any leftover file after `expire_days`, even if
    the normal "delete when the video is ready" step never ran.
    """
    import boto3
    from botocore.exceptions import ClientError

    settings = get_settings()
    if not settings.recordings_storage_configured:
        sys.exit("Xato: .env da RECORDINGS_S3_BUCKET / ACCESS_KEY / SECRET_KEY to'ldirilmagan")
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.recordings_s3_endpoint_url or None,
        region_name=settings.recordings_s3_region,
        aws_access_key_id=settings.recordings_s3_access_key,
        aws_secret_access_key=settings.recordings_s3_secret_key,
    )
    bucket = settings.recordings_s3_bucket
    try:
        s3.head_bucket(Bucket=bucket)
        print(f"Bucket bor: {bucket}")
    except ClientError:
        kwargs = {}
        if settings.recordings_s3_region != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": settings.recordings_s3_region}
        s3.create_bucket(Bucket=bucket, **kwargs)
        print(f"Bucket yaratildi: {bucket}")

    # No public access, ever
    try:
        s3.delete_bucket_policy(Bucket=bucket)
    except ClientError:
        pass
    try:
        s3.put_public_access_block(
            Bucket=bucket,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )
    except ClientError:
        pass  # MinIO does not support this call; its buckets are private by default
    s3.put_bucket_lifecycle_configuration(
        Bucket=bucket,
        LifecycleConfiguration={
            "Rules": [
                {
                    "ID": "expire-raw-recordings",
                    "Status": "Enabled",
                    "Filter": {"Prefix": "recordings/"},
                    "Expiration": {"Days": expire_days},
                }
            ]
        },
    )
    print(f"Bucket yopiq (private), {expire_days} kundan eski fayllar avtomatik o'chiriladi")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    teacher = sub.add_parser("create-teacher", help="O'qituvchi akkaunti yaratish")
    teacher.add_argument("--phone", required=True)
    teacher.add_argument("--name", required=True)
    bucket = sub.add_parser("init-recordings-bucket", help="Yozuvlar uchun yopiq bucket yaratish")
    bucket.add_argument("--expire-days", type=int, default=7)
    args = parser.parse_args()

    if args.command == "init-recordings-bucket":
        init_recordings_bucket(args.expire_days)
        return

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
