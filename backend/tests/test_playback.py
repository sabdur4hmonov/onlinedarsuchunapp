import json

import pytest

from app.models import Lesson, LessonStatus
from tests.conftest import (
    audit_events,
    create_course_with_student,
    create_teacher,
    login_and_bind,
    new_device_id,
    register_student,
)

STUDENT_PHONE = "+998907777777"


async def _setup(client, db, video, *, consent=True, enrolled=True, status=LessonStatus.READY):
    """Teacher + course + lesson with a mock video in `status`, and a logged-in student."""
    student = await register_student(client, STUDENT_PHONE)
    teacher = await create_teacher(db)
    other = await register_student(client, "+998908888888")
    course = await create_course_with_student(db, teacher, student["id"] if enrolled else other["id"])

    upload = await video.create_upload(title="1-dars")
    video.set_status(upload.video_id, status, duration_seconds=600)
    lesson = Lesson(
        course_id=course.id, title="1-dars", position=1, provider="mock", provider_video_id=upload.video_id, status=status
    )
    db.add(lesson)
    await db.commit()

    tokens = await login_and_bind(client, STUDENT_PHONE)
    if consent:
        for t in ("camera", "data_processing"):
            assert (await client.post("/consents", json={"type": t}, headers=tokens.headers())).status_code == 201
    return student, lesson, tokens


async def test_playback_success_returns_otp_with_watermark(client, db, video):
    student, lesson, tokens = await _setup(client, db, video)

    r = await client.post(f"/lessons/{lesson.id}/playback", headers=tokens.headers())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["otp"].startswith("mock-otp-")
    assert body["playback_info"]
    assert 0 < body["expires_in"] <= 300

    sent = video.otp_requests[-1]
    assert sent["video_id"] == lesson.provider_video_id
    assert sent["ttl"] <= 300
    annotation = json.loads(sent["annotate"])
    assert annotation[0]["type"] == "rtext"  # moving text
    assert float(annotation[0]["alpha"]) < 1  # semi-transparent
    assert int(annotation[0]["interval"]) > 0  # changes position periodically
    assert STUDENT_PHONE in annotation[0]["text"]  # full phone number, not masked
    assert student["id"] in annotation[0]["text"]

    granted = await audit_events(db, "playback_granted")
    assert len(granted) == 1
    log = granted[0]
    assert str(log.user_id) == student["id"]
    assert log.details["lesson_id"] == str(lesson.id)
    assert log.details["device_id"] == tokens.device_id
    assert log.ip


async def test_course_content_lists_ready_lessons(client, db, video):
    _, lesson, tokens = await _setup(client, db, video)
    r = await client.get(f"/courses/{lesson.course_id}/content", headers=tokens.headers())
    assert r.status_code == 200
    assert [x["id"] for x in r.json()["lessons"]] == [str(lesson.id)]
    assert "provider_video_id" not in r.json()["lessons"][0]


async def test_not_enrolled_student_is_rejected(client, db, video):
    _, lesson, tokens = await _setup(client, db, video, enrolled=False)
    r = await client.post(f"/lessons/{lesson.id}/playback", headers=tokens.headers())
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "not_enrolled"
    assert video.otp_requests == []
    denied = await audit_events(db, "playback_denied")
    assert [d.details["reason"] for d in denied] == ["not_enrolled"]


async def test_student_without_consent_is_rejected(client, db, video):
    _, lesson, tokens = await _setup(client, db, video, consent=False)
    r = await client.post(f"/lessons/{lesson.id}/playback", headers=tokens.headers())
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "consent_required"
    assert video.otp_requests == []


async def test_token_from_other_device_is_rejected(client, db, video):
    _, lesson, tokens = await _setup(client, db, video)
    r = await client.post(
        f"/lessons/{lesson.id}/playback",
        headers={"Authorization": f"Bearer {tokens.access}", "X-Device-ID": new_device_id()},
    )
    assert r.status_code == 401
    assert video.otp_requests == []


async def test_revoked_session_is_rejected(client, db, video):
    _, lesson, tokens = await _setup(client, db, video)
    await login_and_bind(client, STUDENT_PHONE)  # login elsewhere kills the old session
    r = await client.post(f"/lessons/{lesson.id}/playback", headers=tokens.headers())
    assert r.status_code == 401


@pytest.mark.parametrize("status", [LessonStatus.UPLOADING, LessonStatus.PROCESSING, LessonStatus.FAILED])
async def test_lesson_not_ready_is_rejected(client, db, video, status):
    _, lesson, tokens = await _setup(client, db, video, status=status)
    r = await client.post(f"/lessons/{lesson.id}/playback", headers=tokens.headers())
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "lesson_not_ready"
    assert video.otp_requests == []


async def test_teacher_cannot_request_playback_as_student(client, db, video):
    _, lesson, _ = await _setup(client, db, video)
    teacher_tokens = await login_and_bind(client, "+998900000001")
    assert (await client.post(f"/lessons/{lesson.id}/playback", headers=teacher_tokens.headers())).status_code == 403


async def test_playback_rate_limit(client, db, video):
    from app.api.deps import playback_rate_limiter

    _, lesson, tokens = await _setup(client, db, video)
    playback_rate_limiter.max_attempts = 3
    for _ in range(3):
        assert (await client.post(f"/lessons/{lesson.id}/playback", headers=tokens.headers())).status_code == 200
    r = await client.post(f"/lessons/{lesson.id}/playback", headers=tokens.headers())
    assert r.status_code == 429
    denied = await audit_events(db, "playback_denied")
    assert [d.details["reason"] for d in denied] == ["rate_limited"]
