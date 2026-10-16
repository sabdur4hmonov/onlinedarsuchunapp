from app.models import LessonStatus
from tests.conftest import WEBHOOK_SECRET, audit_events, create_teacher, login_and_bind, register_student


async def _teacher_with_course(client, db, phone="+998900000001"):
    teacher = await create_teacher(db, phone)
    tokens = await login_and_bind(client, teacher.phone)
    r = await client.post("/teacher/courses", json={"title": "Fizika"}, headers=tokens.headers())
    assert r.status_code == 201
    return tokens, r.json()["id"]


async def _create_lesson(client, tokens, course_id, title="1-dars"):
    r = await client.post(f"/teacher/courses/{course_id}/lessons", json={"title": title}, headers=tokens.headers())
    assert r.status_code == 201, r.text
    return r.json()


async def test_teacher_lesson_crud_and_reorder(client, db):
    tokens, course_id = await _teacher_with_course(client, db)
    l1 = await _create_lesson(client, tokens, course_id, "Kirish")
    l2 = await _create_lesson(client, tokens, course_id, "Kinematika")
    l3 = await _create_lesson(client, tokens, course_id, "Dinamika")
    assert [l1["position"], l2["position"], l3["position"]] == [1, 2, 3]
    assert l1["status"] == "uploading"

    r = await client.patch(f"/teacher/lessons/{l2['id']}", json={"title": "Kinematika asoslari"}, headers=tokens.headers())
    assert r.status_code == 200
    assert r.json()["title"] == "Kinematika asoslari"

    r = await client.put(
        f"/teacher/courses/{course_id}/lessons/order",
        json={"lesson_ids": [l3["id"], l1["id"], l2["id"]]},
        headers=tokens.headers(),
    )
    assert r.status_code == 200
    assert [x["id"] for x in r.json()] == [l3["id"], l1["id"], l2["id"]]

    # Incomplete order list is refused
    r = await client.put(
        f"/teacher/courses/{course_id}/lessons/order", json={"lesson_ids": [l1["id"]]}, headers=tokens.headers()
    )
    assert r.status_code == 400

    assert (await client.delete(f"/teacher/lessons/{l3['id']}", headers=tokens.headers())).status_code == 204
    r = await client.get(f"/teacher/courses/{course_id}/lessons", headers=tokens.headers())
    assert [(x["id"], x["position"]) for x in r.json()] == [(l1["id"], 1), (l2["id"], 2)]


async def test_teacher_cannot_add_lesson_to_other_teachers_course(client, db):
    owner_tokens, course_id = await _teacher_with_course(client, db, "+998900000001")
    lesson = await _create_lesson(client, owner_tokens, course_id)
    stranger = await create_teacher(db, "+998900000002")
    st = await login_and_bind(client, stranger.phone)

    r = await client.post(f"/teacher/courses/{course_id}/lessons", json={"title": "Begona"}, headers=st.headers())
    assert r.status_code == 404
    # ...nor edit, delete, reorder or upload into it
    assert (await client.patch(f"/teacher/lessons/{lesson['id']}", json={"title": "x"}, headers=st.headers())).status_code == 404
    assert (await client.delete(f"/teacher/lessons/{lesson['id']}", headers=st.headers())).status_code == 404
    assert (await client.post(f"/teacher/lessons/{lesson['id']}/video-upload", headers=st.headers())).status_code == 404
    r = await client.put(
        f"/teacher/courses/{course_id}/lessons/order", json={"lesson_ids": [lesson["id"]]}, headers=st.headers()
    )
    assert r.status_code == 404


async def test_student_cannot_manage_lessons(client, db):
    await register_student(client, "+998906666666")
    st = await login_and_bind(client, "+998906666666")
    _, course_id = await _teacher_with_course(client, db)
    r = await client.post(f"/teacher/courses/{course_id}/lessons", json={"title": "x"}, headers=st.headers())
    assert r.status_code == 403


async def test_video_upload_returns_direct_upload_credentials(client, db, video):
    tokens, course_id = await _teacher_with_course(client, db)
    lesson = await _create_lesson(client, tokens, course_id)

    r = await client.post(f"/teacher/lessons/{lesson['id']}/video-upload", headers=tokens.headers())
    assert r.status_code == 200
    body = r.json()
    assert body["upload_url"].startswith("https://")
    assert body["fields"]
    assert body["lesson"]["provider"] == "mock"
    assert body["lesson"]["provider_video_id"] in video.videos
    assert body["lesson"]["status"] == "uploading"
    assert len(await audit_events(db, "video_upload_started")) == 1


async def _uploaded_lesson(client, db, video):
    tokens, course_id = await _teacher_with_course(client, db)
    lesson = await _create_lesson(client, tokens, course_id)
    r = await client.post(f"/teacher/lessons/{lesson['id']}/video-upload", headers=tokens.headers())
    return tokens, r.json()["lesson"]


def _webhook_body(video_id, status="ready"):
    return {"event": "video:ready", "payload": {"id": video_id, "status": status}}


async def test_valid_webhook_marks_lesson_ready(client, db, video):
    tokens, lesson = await _uploaded_lesson(client, db, video)
    video.set_status(lesson["provider_video_id"], LessonStatus.READY, duration_seconds=754)

    r = await client.post(f"/webhooks/vdocipher?token={WEBHOOK_SECRET}", json=_webhook_body(lesson["provider_video_id"]))
    assert r.status_code == 200
    assert r.json()["lesson_status"] == "ready"

    r = await client.get(f"/teacher/courses/{lesson['course_id']}/lessons", headers=tokens.headers())
    assert r.json()[0]["status"] == "ready"
    assert r.json()[0]["duration_seconds"] == 754
    assert len(await audit_events(db, "video_status_updated")) == 1


async def test_fake_webhook_is_rejected(client, db, video):
    tokens, lesson = await _uploaded_lesson(client, db, video)
    video.set_status(lesson["provider_video_id"], LessonStatus.READY, duration_seconds=10)
    body = _webhook_body(lesson["provider_video_id"])

    assert (await client.post("/webhooks/vdocipher", json=body)).status_code == 401
    assert (await client.post("/webhooks/vdocipher?token=wrong-secret", json=body)).status_code == 401
    assert (await client.post("/webhooks/vdocipher", json=body, headers={"X-Webhook-Token": "nope"})).status_code == 401

    r = await client.get(f"/teacher/courses/{lesson['course_id']}/lessons", headers=tokens.headers())
    assert r.json()[0]["status"] == "uploading"  # nothing changed
    assert len(await audit_events(db, "webhook_rejected")) == 3


async def test_webhook_body_cannot_fake_ready_status(client, db, video):
    """Even with the right token, the status comes from the provider API, not from the request."""
    tokens, lesson = await _uploaded_lesson(client, db, video)
    video.set_status(lesson["provider_video_id"], LessonStatus.PROCESSING)

    r = await client.post(
        f"/webhooks/vdocipher?token={WEBHOOK_SECRET}", json=_webhook_body(lesson["provider_video_id"], "ready")
    )
    assert r.status_code == 200
    assert r.json()["lesson_status"] == "processing"


async def test_webhook_rejected_when_secret_not_configured(client, db, video, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "vdocipher_webhook_secret", "")
    _, lesson = await _uploaded_lesson(client, db, video)
    r = await client.post("/webhooks/vdocipher?token=", json=_webhook_body(lesson["provider_video_id"]))
    assert r.status_code == 401


async def test_webhook_for_unknown_video_is_ignored(client):
    r = await client.post(f"/webhooks/vdocipher?token={WEBHOOK_SECRET}", json=_webhook_body("not-ours"))
    assert r.status_code == 200
    assert r.json()["status"] == "ignored"


async def test_deleting_lesson_deletes_provider_video(client, db, video):
    tokens, lesson = await _uploaded_lesson(client, db, video)
    assert (await client.delete(f"/teacher/lessons/{lesson['id']}", headers=tokens.headers())).status_code == 204
    assert video.deleted == [lesson["provider_video_id"]]
