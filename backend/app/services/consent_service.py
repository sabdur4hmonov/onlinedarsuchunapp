import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Consent, ConsentType
from app.services.audit import AuditEvent, log_event

# Without these a student cannot open any course content
REQUIRED_FOR_CONTENT = (ConsentType.CAMERA, ConsentType.DATA_PROCESSING)


async def list_consents(db: AsyncSession, user_id: uuid.UUID) -> list[Consent]:
    return list(await db.scalars(select(Consent).where(Consent.user_id == user_id).order_by(Consent.granted_at)))


async def grant(db: AsyncSession, *, user_id: uuid.UUID, consent_type: ConsentType, ip: str | None) -> None:
    """Records consent for the CURRENT text version. Repeating it is harmless."""
    version = get_settings().consent_version
    result = await db.execute(
        insert(Consent)
        .values(id=uuid.uuid4(), user_id=user_id, type=consent_type, version=version)
        .on_conflict_do_nothing(constraint="uq_consents_user_id_type_version")
    )
    if result.rowcount:
        log_event(db, AuditEvent.CONSENT_GRANTED, user_id=user_id, ip=ip, type=consent_type, version=version)
    await db.commit()


async def missing_for_content(db: AsyncSession, user_id: uuid.UUID) -> list[ConsentType]:
    version = get_settings().consent_version
    granted = set(
        await db.scalars(
            select(Consent.type).where(
                Consent.user_id == user_id, Consent.version == version, Consent.type.in_(REQUIRED_FOR_CONTENT)
            )
        )
    )
    return [t for t in REQUIRED_FOR_CONTENT if t not in granted]
