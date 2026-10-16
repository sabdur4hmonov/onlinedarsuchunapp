import hmac
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request
from sqlalchemy import select

from app.api.deps import ClientIp, DbSession, VideoProviderDep
from app.core.config import get_settings
from app.core.errors import api_error
from app.models import Lesson
from app.services import lesson_service
from app.services.audit import AuditEvent, log_event

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _token_is_valid(token: str | None) -> bool:
    secret = get_settings().vdocipher_webhook_secret
    # No secret configured -> every webhook is rejected (never "open by default")
    if not secret or not token:
        return False
    return hmac.compare_digest(token.encode(), secret.encode())


@router.post("/vdocipher")
async def vdocipher_webhook(
    request: Request,
    db: DbSession,
    ip: ClientIp,
    provider: VideoProviderDep,
    token: Annotated[str | None, Query()] = None,
    x_webhook_token: Annotated[str | None, Header(alias="X-Webhook-Token")] = None,
):
    """Called by VdoCipher when a video changes state (e.g. `video:ready`).

    Register it in VdoCipher as: https://<your-domain>/webhooks/vdocipher?token=<VDOCIPHER_WEBHOOK_SECRET>

    Two layers of protection against forged calls:
    1. the secret token must match;
    2. the body is used only to learn WHICH video changed — the new status is
       fetched from the VdoCipher API itself, never trusted from the request.
    """
    if not _token_is_valid(token or x_webhook_token):
        log_event(db, AuditEvent.WEBHOOK_REJECTED, ip=ip, provider="vdocipher", reason="invalid_token")
        await db.commit()
        raise api_error(401, "invalid_webhook_token", "Webhook token noto'g'ri")

    try:
        payload = await request.json()
    except ValueError:
        raise api_error(400, "invalid_payload", "JSON kutilgan edi") from None
    video_id = provider.parse_webhook(payload) if isinstance(payload, dict) else None
    if video_id is None:
        return {"status": "ignored"}

    lesson = await db.scalar(
        select(Lesson).where(Lesson.provider == provider.name, Lesson.provider_video_id == video_id).with_for_update()
    )
    if lesson is None:
        # Not ours (or already deleted). Answer 200 so the provider does not retry forever.
        return {"status": "ignored"}

    await lesson_service.sync_video_status(db, lesson=lesson, provider=provider, ip=ip, source="webhook")
    return {"status": "ok", "lesson_status": lesson.status}
