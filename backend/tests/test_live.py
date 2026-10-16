import base64
import hashlib

import jwt
import pytest
from google.protobuf.json_format import MessageToJson
from livekit import api as lk

from app.models import LessonStatus
from tests.conftest import (
    LIVEKIT_TEST_KEY,
    LIVEKIT_TEST_SECRET,
    WEBHOOK_SECRET,
    audit_events,
    create_course_with_student,
    create_teacher,
    login_and_bind,
    new_device_id,
    register_student,
)

STUDENT_PHONE = "+998909999999"
TEACHER_PHONE = "+998900000001"


# ---------- helpers ----------


def signed_webhook(event: lk.WebhookEvent, *, secret: str = LIVEKIT_TEST_SECRET, body: str | None = None):
    """Builds a webhook exactly like LiveKit does: JWT in Authorization with sha256 of the body."""
    real_body = MessageToJson(event)
    digest = base64.b64encode(hashlib.sha256(real_body.encode()).digest()).decode()
    token = lk.AccessToken(LIVEKIT_TEST_KEY, secret).with_sha256(digest).to_jwt()
    return (body if body is not None else real_body), {"Authorization": token, "Content-Type": "application/webhook+json"}


async def send_webhook(client, event: lk.WebhookEvent, **kwargs):
    body, headers = signed_webhook(event, **kwargs)
    return await client.post("/webhooks/livekit", content=body, headers=headers)


def decode_livekit_token(token: str, live) -> dict:
    return jwt.decode(token, live.api_secret, algorithms=["HS256"], issuer=live.api_key)


async def _teacher_course_student(client, db, *, consent=True, enrolled=True):
    """Teacher with a course, a student (enrolled or not, with or without consent) and a scheduled live session."""
    student = await register_student(client, STUDENT_PHONE)
    teacher = await create_teacher(db, TEACHER_PHONE)
    other = await register_student(client, "+998908888888")
    course = await create_course_with_student(db, teacher, student["id"] if enrolled else other["id"])
    teacher_tokens = await login_and_bind(client, teacher.phone)
    r = await client.post(
        f"/teacher/courses/{course.id}/live-sessions",
        json={"title": "Algebra jonli", "scheduled_at": "2026-10-20T15:00:00+05:00"},
        headers=teacher_tokens.headers(),
    )
    assert r.status_code == 201, r.text
    student_tokens = await login_and_bind(client, STUDENT_PHONE)
    if consent:
        for t in ("camera", "data_processing"):
            await client.post("/consents", json={"type": t}, headers=student_tokens.headers())
    return {"teacher": teacher_tokens, "student": student_tokens, "student_id": student["id"], "session": r.json()}


async def _start(client, ctx):
    r = await client.post(f"/teacher/live-sessions/{ctx['session']['id']}/start", headers=ctx["teacher"].headers())
    assert r.status_code == 200, r.text
    return r.json()


# ---------- teacher ----------


async def test_teacher_schedule_edit_cancel(client, db):
    ctx = await _teacher_course_student(client, db)
    sid = ctx["session"]["id"]
    assert ctx["session"]["status"] == "scheduled"
    assert "room_name" not in ctx["session"]

    r = await client.patch(f"/teacher/live-sessions/{sid}", json={"title": "Algebra 2"}, headers=ctx["teacher"].headers())
    assert r.status_code == 200 and r.json()["title"] == "Algebra 2"

    r = await client.post(f"/teacher/live-sessions/{sid}/cancel", headers=ctx["teacher"].headers())
    assert r.json()["status"] == "cancelled"
    # Cancelled lesson can be neither edited nor started
    assert (await client.patch(f"/teacher/live-sessions/{sid}", json={"title": "x"}, headers=ctx["teacher"].headers())).status_code == 409
    assert (await client.post(f"/teacher/live-sessions/{sid}/start", headers=ctx["teacher"].headers())).status_code == 409


async def test_start_creates_room_records_automatically_and_gives_publish_token(client, db, live):
    ctx = await _teacher_course_student(client, db)
    body = await _start(client, ctx)

    assert body["live_session"]["status"] == "live"
    assert body["live_session"]["recording_status"] == "recording"
    assert body["client_options"] == {"adaptive_stream": True, "dynacast": True, "simulcast": True, "auto_subscribe": True}

    [(room_name, room)] = live.rooms.items()
    assert room["empty_timeout"] >= 600 and room["departure_timeout"] >= 600
    assert room_name.startswith("live-") and len(room_name) > 30  # random, not guessable
    [(_, recording)] = live.recordings.items()
    assert recording["room_name"] == room_name and recording["object_key"].endswith(".mp4")

    claims = decode_livekit_token(body["token"], live)
    assert claims["video"]["canPublish"] is True
    assert claims["video"]["room"] == room_name

    # Calling start again (teacher app restarted) only gives a new token
    again = await _start(client, ctx)
    assert again["token"] and len(live.rooms) == 1 and len(live.recordings) == 1


async def test_teacher_cannot_start_other_teachers_session(client, db, live):
    ctx = await _teacher_course_student(client, db)
    stranger = await create_teacher(db, "+998900000002")
    st = await login_and_bind(client, stranger.phone)

    sid = ctx["session"]["id"]
    assert (await client.post(f"/teacher/live-sessions/{sid}/start", headers=st.headers())).status_code == 404
    assert (await client.post(f"/teacher/live-sessions/{sid}/cancel", headers=st.headers())).status_code == 404
    r = await client.post(
        f"/teacher/courses/{ctx['session']['course_id']}/live-sessions",
        json={"title": "Begona", "scheduled_at": "2026-10-20T15:00:00+05:00"},
        headers=st.headers(),
    )
    assert r.status_code == 404
    assert live.rooms == {}


async def test_end_stops_recording_and_closes_room(client, db, live):
    ctx = await _teacher_course_student(client, db)
    await _start(client, ctx)
    r = await client.post(f"/teacher/live-sessions/{ctx['session']['id']}/end", headers=ctx["teacher"].headers())
    assert r.status_code == 200
    assert r.json()["status"] == "ended"
    assert r.json()["recording_status"] == "uploading"
    assert live.rooms == {} and len(live.deleted_rooms) == 1
    assert all(not rec["active"] for rec in live.recordings.values())


# ---------- student join ----------


async def test_student_join_gets_subscribe_only_token_and_watermark(client, db, live):
    ctx = await _teacher_course_student(client, db)
    await _start(client, ctx)

    r = await client.post(f"/live-sessions/{ctx['session']['id']}/join", headers=ctx["student"].headers())
    assert r.status_code == 200, r.text
    body = r.json()

    claims = decode_livekit_token(body["token"], live)
    grants = claims["video"]
    assert grants["roomJoin"] is True
    assert grants["canSubscribe"] is True
    assert grants["canPublish"] is False  # no camera / microphone / screen share
    assert grants["canPublishData"] is False
    assert claims["sub"] == ctx["student_id"] == body["identity"]  # identity = user ID
    assert claims["exp"] - claims["nbf"] <= 10 * 60

    assert body["watermark"]["user_id"] == ctx["student_id"]
    assert body["watermark"]["phone"] == STUDENT_PHONE
    assert STUDENT_PHONE in body["watermark"]["text"]
    assert "room_name" not in body["live_session"]

    granted = await audit_events(db, "live_join_granted")
    assert len(granted) == 1
    assert granted[0].details["device_id"] == ctx["student"].device_id
    assert granted[0].ip


async def test_not_enrolled_student_cannot_join(client, db):
    ctx = await _teacher_course_student(client, db, enrolled=False)
    await _start(client, ctx)
    r = await client.post(f"/live-sessions/{ctx['session']['id']}/join", headers=ctx["student"].headers())
    assert r.status_code == 403 and r.json()["detail"]["code"] == "not_enrolled"
    assert [d.details["reason"] for d in await audit_events(db, "live_join_denied")] == ["not_enrolled"]


async def test_student_without_consent_cannot_join(client, db):
    ctx = await _teacher_course_student(client, db, consent=False)
    await _start(client, ctx)
    r = await client.post(f"/live-sessions/{ctx['session']['id']}/join", headers=ctx["student"].headers())
    assert r.status_code == 403 and r.json()["detail"]["code"] == "consent_required"


async def test_student_token_from_other_device_cannot_join(client, db):
    ctx = await _teacher_course_student(client, db)
    await _start(client, ctx)
    headers = {"Authorization": f"Bearer {ctx['student'].access}", "X-Device-ID": new_device_id()}
    assert (await client.post(f"/live-sessions/{ctx['session']['id']}/join", headers=headers)).status_code == 401


@pytest.mark.parametrize("final_action", [None, "cancel", "end"])
async def test_join_rejected_when_not_live(client, db, final_action):
    ctx = await _teacher_course_student(client, db)
    sid = ctx["session"]["id"]
    if final_action == "cancel":
        await client.post(f"/teacher/live-sessions/{sid}/cancel", headers=ctx["teacher"].headers())
    elif final_action == "end":
        await _start(client, ctx)
        await client.post(f"/teacher/live-sessions/{sid}/end", headers=ctx["teacher"].headers())
    r = await client.post(f"/live-sessions/{sid}/join", headers=ctx["student"].headers())
    assert r.status_code == 409 and r.json()["detail"]["code"] == "live_session_not_live"


async def test_student_sees_course_live_sessions(client, db):
    ctx = await _teacher_course_student(client, db)
    r = await client.get(f"/courses/{ctx['session']['course_id']}/live-sessions", headers=ctx["student"].headers())
    assert r.status_code == 200
    assert [x["id"] for x in r.json()] == [ctx["session"]["id"]]


# ---------- LiveKit webhook ----------


def _room_event(event: str, room_name: str, identity: str | None = None) -> lk.WebhookEvent:
    ev = lk.WebhookEvent(event=event, room=lk.Room(name=room_name), id="EV_test")
    if identity:
        ev.participant.CopyFrom(lk.ParticipantInfo(identity=identity))
    return ev


async def test_fake_livekit_webhook_is_rejected(client, db, live):
    ctx = await _teacher_course_student(client, db)
    await _start(client, ctx)
    room_name = next(iter(live.rooms))
    event = _room_event("room_finished", room_name)

    # 1) no signature
    r = await client.post("/webhooks/livekit", content=MessageToJson(event), headers={"Content-Type": "application/webhook+json"})
    assert r.status_code == 401
    # 2) signed with a wrong secret
    assert (await send_webhook(client, event, secret="attacker-secret-0123456789abcdefgh")).status_code == 401
    # 3) valid signature, but the body was modified after signing
    tampered = MessageToJson(_room_event("room_finished", "live-some-other-room"))
    assert (await send_webhook(client, event, body=tampered)).status_code == 401

    assert len(await audit_events(db, "livekit_webhook_rejected")) == 3
    r = await client.get(f"/teacher/live-sessions/{ctx['session']['id']}", headers=ctx["teacher"].headers())
    assert r.json()["status"] == "live"  # nothing changed


async def test_signed_webhooks_are_audited_and_room_finished_ends_session(client, db, live):
    ctx = await _teacher_course_student(client, db)
    await _start(client, ctx)
    room_name = next(iter(live.rooms))

    assert (await send_webhook(client, _room_event("room_started", room_name))).status_code == 200
    r = await send_webhook(client, _room_event("participant_joined", room_name, ctx["student_id"]))
    assert r.status_code == 200
    await send_webhook(client, _room_event("participant_left", room_name, ctx["student_id"]))
    joined = await audit_events(db, "live_participant_joined")
    assert len(joined) == 1 and str(joined[0].user_id) == ctx["student_id"]
    assert len(await audit_events(db, "live_participant_left")) == 1

    # Room closed by LiveKit (e.g. empty timeout) -> lesson is over
    await send_webhook(client, _room_event("room_finished", room_name))
    r = await client.get(f"/teacher/live-sessions/{ctx['session']['id']}", headers=ctx["teacher"].headers())
    assert r.json()["status"] == "ended"


# ---------- recording -> lesson ----------


def _egress_ended(egress_id: str, status=lk.EgressStatus.EGRESS_COMPLETE, error: str = "") -> lk.WebhookEvent:
    return lk.WebhookEvent(
        event="egress_ended",
        id="EV_egress",
        egress_info=lk.EgressInfo(egress_id=egress_id, status=status, error=error),
    )


async def _ended_with_recording(client, ctx, live, storage):
    await _start(client, ctx)
    await client.post(f"/teacher/live-sessions/{ctx['session']['id']}/end", headers=ctx["teacher"].headers())
    [(egress_id, recording)] = live.recordings.items()
    storage.put(recording["object_key"])  # the recorder uploaded the mp4
    return egress_id, recording["object_key"]


async def _session(client, ctx):
    r = await client.get(f"/teacher/live-sessions/{ctx['session']['id']}", headers=ctx["teacher"].headers())
    return r.json()


async def test_recording_becomes_lesson_and_temp_file_is_deleted(client, db, live, storage, video):
    ctx = await _teacher_course_student(client, db)
    egress_id, key = await _ended_with_recording(client, ctx, live, storage)

    assert (await send_webhook(client, _egress_ended(egress_id))).status_code == 200

    session = await _session(client, ctx)
    assert session["recording_status"] == "processing"
    lesson_id = session["resulting_lesson_id"]
    assert lesson_id

    # Imported through a short-lived presigned URL (never a public link)
    [imported] = video.imports
    assert "X-Amz-Signature" in imported["url"]
    assert storage.presigned[-1]["ttl_seconds"] <= 6 * 3600
    assert imported["title"].startswith("Algebra jonli — ")
    assert key in storage.objects  # not deleted yet: video not ready

    lessons = (await client.get(f"/teacher/courses/{session['course_id']}/lessons", headers=ctx["teacher"].headers())).json()
    assert [x["id"] for x in lessons] == [lesson_id]
    assert lessons[0]["status"] == "processing"

    # VdoCipher finished encoding -> its webhook -> lesson ready -> raw mp4 deleted
    video.set_status(imported["video_id"], LessonStatus.READY, duration_seconds=3600)
    r = await client.post(
        f"/webhooks/vdocipher?token={WEBHOOK_SECRET}", json={"event": "video:ready", "payload": {"id": imported["video_id"]}}
    )
    assert r.status_code == 200 and r.json()["lesson_status"] == "ready"

    assert key not in storage.objects and storage.deleted == [key]
    session = await _session(client, ctx)
    assert session["recording_status"] == "ready"
    assert len(await audit_events(db, "recording_temp_file_deleted")) == 1
    assert len(await audit_events(db, "recording_ready")) == 1

    # Duplicate egress_ended delivery does not create a second lesson
    await send_webhook(client, _egress_ended(egress_id))
    assert len(video.imports) == 1


async def test_recording_import_failure_then_retry(client, db, live, storage, video):
    ctx = await _teacher_course_student(client, db)
    egress_id, key = await _ended_with_recording(client, ctx, live, storage)

    video.fail_import = True
    await send_webhook(client, _egress_ended(egress_id))
    session = await _session(client, ctx)
    assert session["recording_status"] == "failed"
    assert session["recording_error"].startswith("video_import:")
    failed = await audit_events(db, "recording_failed")
    assert len(failed) == 1 and failed[0].details["step"] == "video_import"
    assert key in storage.objects  # the file is kept for the retry

    # Provider is back -> teacher retries
    video.fail_import = False
    r = await client.post(f"/teacher/live-sessions/{ctx['session']['id']}/recording/retry", headers=ctx["teacher"].headers())
    assert r.status_code == 200, r.text
    assert r.json()["recording_status"] == "processing"
    assert r.json()["recording_error"] is None
    assert len(await audit_events(db, "recording_retry")) == 1

    # ...and the rest of the pipeline still works
    video.set_status(video.imports[-1]["video_id"], LessonStatus.READY, duration_seconds=60)
    lesson_id = r.json()["resulting_lesson_id"]
    r = await client.post(f"/teacher/lessons/{lesson_id}/sync-status", headers=ctx["teacher"].headers())
    assert r.json()["status"] == "ready"
    assert (await _session(client, ctx))["recording_status"] == "ready"
    assert key not in storage.objects


async def test_temp_file_delete_failure_is_failed_and_retryable(client, db, live, storage, video):
    ctx = await _teacher_course_student(client, db)
    egress_id, key = await _ended_with_recording(client, ctx, live, storage)
    await send_webhook(client, _egress_ended(egress_id))
    video.set_status(video.imports[-1]["video_id"], LessonStatus.READY)

    storage.fail_delete = True
    await client.post(
        f"/webhooks/vdocipher?token={WEBHOOK_SECRET}", json={"payload": {"id": video.imports[-1]["video_id"]}}
    )
    session = await _session(client, ctx)
    assert session["recording_status"] == "failed"  # an unprotected copy still exists
    assert session["recording_error"].startswith("storage_delete:")

    storage.fail_delete = False
    r = await client.post(f"/teacher/live-sessions/{ctx['session']['id']}/recording/retry", headers=ctx["teacher"].headers())
    assert r.json()["recording_status"] == "ready"
    assert key not in storage.objects
    assert len(video.imports) == 1  # no second import


async def test_egress_failure_marks_failed_and_retry_during_live_restarts_recorder(client, db, live, storage):
    ctx = await _teacher_course_student(client, db)
    await _start(client, ctx)
    [first_egress] = live.recordings

    await send_webhook(client, _egress_ended(first_egress, status=lk.EgressStatus.EGRESS_FAILED, error="chrome crashed"))
    session = await _session(client, ctx)
    assert session["status"] == "live"
    assert session["recording_status"] == "failed"
    assert "EGRESS_FAILED" in session["recording_error"]

    r = await client.post(f"/teacher/live-sessions/{ctx['session']['id']}/recording/retry", headers=ctx["teacher"].headers())
    assert r.status_code == 200 and r.json()["recording_status"] == "recording"
    assert len(live.recordings) == 2


async def test_recording_start_failure_does_not_block_lesson(client, db, live):
    live.fail_recording_start = True
    ctx = await _teacher_course_student(client, db)
    body = await _start(client, ctx)
    assert body["live_session"]["status"] == "live"
    assert body["live_session"]["recording_status"] == "failed"
    assert body["live_session"]["recording_error"].startswith("egress_start:")

    live.fail_recording_start = False
    r = await client.post(f"/teacher/live-sessions/{ctx['session']['id']}/recording/retry", headers=ctx["teacher"].headers())
    assert r.json()["recording_status"] == "recording"


async def test_retry_without_file_after_lesson_is_not_recoverable(client, db, live):
    live.fail_recording_start = True
    ctx = await _teacher_course_student(client, db)
    await _start(client, ctx)
    await client.post(f"/teacher/live-sessions/{ctx['session']['id']}/end", headers=ctx["teacher"].headers())
    r = await client.post(f"/teacher/live-sessions/{ctx['session']['id']}/recording/retry", headers=ctx["teacher"].headers())
    assert r.status_code == 409 and r.json()["detail"]["code"] == "recording_not_recoverable"


async def test_retry_only_when_failed(client, db):
    ctx = await _teacher_course_student(client, db)
    r = await client.post(f"/teacher/live-sessions/{ctx['session']['id']}/recording/retry", headers=ctx["teacher"].headers())
    assert r.status_code == 409 and r.json()["detail"]["code"] == "recording_not_failed"
