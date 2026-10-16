import hmac
import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request
from sqlalchemy import select

from livekit import api as lk

from app.api.deps import ClientIp, DbSession, RecordingStorageDep, VideoProviderDep
from app.core.config import get_settings
from app.core.errors import api_error
from app.models import Lesson, LiveSession, LiveSessionStatus
from app.services import lesson_service, recording_service
from app.services.audit import AuditEvent, log_event
from app.services.live.webhook import InvalidWebhook, verify_livekit_webhook

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
    storage: RecordingStorageDep,
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
    # If this lesson is a live recording: video ready -> delete the raw mp4 from temporary storage
    await recording_service.on_lesson_video_status(db, lesson, storage=storage, ip=ip)
    return {"status": "ok", "lesson_status": lesson.status}


# LiveKit egress states after which the mp4 file is complete and uploaded
_EGRESS_FILE_DONE = {lk.EgressStatus.EGRESS_COMPLETE, lk.EgressStatus.EGRESS_LIMIT_REACHED}


def _user_id_or_none(identity: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(identity)
    except ValueError:
        return None  # e.g. the egress recorder's own identity


@router.post("/livekit")
async def livekit_webhook(
    request: Request,
    db: DbSession,
    ip: ClientIp,
    video: VideoProviderDep,
    storage: RecordingStorageDep,
    authorization: Annotated[str | None, Header()] = None,
):
    """LiveKit server events. Register in LiveKit config: webhook.urls = https://<domain>/webhooks/livekit

    The signature is verified with the official SDK (`WebhookReceiver`); forged or
    modified requests get 401 and are audited.
    """
    try:
        body = (await request.body()).decode("utf-8")
        event = verify_livekit_webhook(body, authorization)
    except (InvalidWebhook, UnicodeDecodeError) as e:
        log_event(db, AuditEvent.LIVEKIT_WEBHOOK_REJECTED, ip=ip, reason=str(e) or e.__class__.__name__)
        await db.commit()
        raise api_error(401, "invalid_webhook_signature", "Webhook imzosi noto'g'ri") from None

    if event.event == "egress_ended":
        info = event.egress_info
        await recording_service.handle_egress_ended(
            db,
            egress_id=info.egress_id,
            completed=info.status in _EGRESS_FILE_DONE,
            egress_status=lk.EgressStatus.Name(info.status),
            error=info.error,
            video=video,
            storage=storage,
            ip=ip,
        )
        return {"status": "ok"}

    room_name = event.room.name
    live = (
        await db.scalar(select(LiveSession).where(LiveSession.room_name == room_name).with_for_update())
        if room_name
        else None
    )
    if live is None:
        return {"status": "ignored"}

    if event.event == "room_started":
        log_event(db, AuditEvent.LIVE_ROOM_STARTED, ip=ip, live_session_id=live.id)
    elif event.event == "room_finished":
        log_event(db, AuditEvent.LIVE_ROOM_FINISHED, ip=ip, live_session_id=live.id)
        if live.status == LiveSessionStatus.LIVE:
            # Room closed without the teacher pressing "end" (e.g. the empty timeout passed)
            recording_service.mark_room_closed(live)
            log_event(db, AuditEvent.LIVE_SESSION_ENDED, ip=ip, live_session_id=live.id, source="room_finished")
    elif event.event in ("participant_joined", "participant_left"):
        identity = event.participant.identity
        log_event(
            db,
            AuditEvent.LIVE_PARTICIPANT_JOINED if event.event == "participant_joined" else AuditEvent.LIVE_PARTICIPANT_LEFT,
            user_id=_user_id_or_none(identity),
            ip=ip,
            live_session_id=live.id,
            identity=identity,
        )
    await db.commit()
    return {"status": "ok"}
