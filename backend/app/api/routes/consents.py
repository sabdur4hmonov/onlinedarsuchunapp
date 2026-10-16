from fastapi import APIRouter

from app.api.deps import Auth, ClientIp, DbSession
from app.schemas.course import ConsentCreate, ConsentOut
from app.services import consent_service

router = APIRouter(prefix="/consents", tags=["consents"])


@router.get("", response_model=list[ConsentOut])
async def my_consents(auth: Auth, db: DbSession):
    return await consent_service.list_consents(db, auth.user.id)


@router.post("", response_model=list[ConsentOut], status_code=201)
async def give_consent(body: ConsentCreate, auth: Auth, db: DbSession, ip: ClientIp):
    """Saves consent for the current version of the consent text (server decides the version)."""
    await consent_service.grant(db, user_id=auth.user.id, consent_type=body.type, ip=ip)
    return await consent_service.list_consents(db, auth.user.id)
