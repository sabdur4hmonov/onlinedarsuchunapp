"""Endpoints added for the teacher web panel."""

from app.core.config import get_settings
from app.models import LessonStatus
from app.services.video import MockVideoProvider
from tests.conftest import (
    PASSWORD,
    audit_events,
    create_course_with_student,
    create_teacher,
    login,
    login_and_bind,
    new_device_id,
    register_student,
)

STUDENT_PHONE = "+998901212121"


async def _teacher(client, db, phone="+998900000001"):
    teacher = await create_teacher(db, phone)
    return teacher, await login_and_bind(client, teacher.phone)


async def _course(client, tokens, title="Kimyo"):
    r = await client.post("/teacher/courses", json={"title": title}, headers=tokens.headers())
    assert r.status_code == 201
    return r.json()


# ---------- courses ----------


async def test_get_and_update_own_course_only(client, db):
    _, owner = await _teacher(client, db)
    _, stranger = await _teacher(client, db, "+998900000002")
    course = await _course(client, owner)

    r = await client.patch(f"/teacher/courses/{course['id']}", json={"title": "Kimyo 2"}, headers=owner.headers())
    assert r.status_code == 200 and r.json()["title"] == "Kimyo 2"
    assert (await client.get(f"/teacher/courses/{course['id']}", headers=owner.headers())).json()["title"] == "Kimyo 2"

    assert (await client.get(f"/teacher/courses/{course['id']}", headers=stranger.headers())).status_code == 404
    r = await client.patch(f"/teacher/courses/{course['id']}", json={"title": "x"}, headers=stranger.headers())
    assert r.status_code == 404
    r = await client.patch(f"/teacher/courses/{course['id']}", json={"title": None}, headers=owner.headers())
    assert r.status_code == 422
    assert len(await audit_events(db, "course_updated")) == 1


# ---------- students ----------


async def test_list_add_and_remove_students(client, db):
    _, owner = await _teacher(client, db)
    _, stranger = await _teacher(client, db, "+998900000002")
    course = await _course(client, owner)
    student = await register_student(client, STUDENT_PHONE)
    await login_and_bind(client, STUDENT_PHONE)

    r = await client.post(
        f"/teacher/courses/{course['id']}/enrollments", json={"student_phone": "90 121 21 21"}, headers=owner.headers()
    )
    assert r.status_code == 201

    r = await client.get(f"/teacher/courses/{course['id']}/students", headers=owner.headers())
    assert r.status_code == 200
    [row] = r.json()
    assert row["id"] == student["id"] and row["phone"] == STUDENT_PHONE and row["active_devices"] == 1

    # Another teacher sees nothing and cannot remove
    assert (await client.get(f"/teacher/courses/{course['id']}/students", headers=stranger.headers())).status_code == 404
    r = await client.delete(f"/teacher/courses/{course['id']}/students/{student['id']}", headers=stranger.headers())
    assert r.status_code == 404

    r = await client.delete(f"/teacher/courses/{course['id']}/students/{student['id']}", headers=owner.headers())
    assert r.status_code == 204
    assert (await client.get(f"/teacher/courses/{course['id']}/students", headers=owner.headers())).json() == []
    assert (await client.delete(f"/teacher/courses/{course['id']}/students/{student['id']}", headers=owner.headers())).status_code == 404
    assert len(await audit_events(db, "student_enrolled")) == 1
    assert len(await audit_events(db, "student_removed")) == 1


# ---------- events journal ----------


async def test_course_events_show_only_this_course(client, db):
    teacher, owner = await _teacher(client, db)
    other_teacher, other = await _teacher(client, db, "+998900000002")
    student = await register_student(client, STUDENT_PHONE)
    outsider = await register_student(client, "+998901313131")
    course = await create_course_with_student(db, teacher, student["id"])
    other_course = await create_course_with_student(db, other_teacher, outsider["id"])

    # Student of this course: failed login + device events
    await client.post("/auth/login", json={"phone": STUDENT_PHONE, "password": "wrong-pass"}, headers={"X-Device-ID": new_device_id()})
    await login_and_bind(client, STUDENT_PHONE)
    await client.post(f"/teacher/students/{student['id']}/devices/reset", json={}, headers=owner.headers())
    # Outsider (other teacher's course): must NOT appear
    await client.post("/auth/login", json={"phone": "+998901313131", "password": "wrong-pass"}, headers={"X-Device-ID": new_device_id()})

    r = await client.get(f"/teacher/courses/{course.id}/events", headers=owner.headers())
    assert r.status_code == 200
    events = r.json()
    types = [e["event_type"] for e in events]
    assert {"login_failed", "device_bound", "device_reset"} <= set(types)
    assert all(e["actor"] is None or e["actor"]["phone"] != "+998901313131" for e in events)
    assert [e["id"] for e in events] == sorted((e["id"] for e in events), reverse=True)  # newest first
    failed = next(e for e in events if e["event_type"] == "login_failed")
    assert failed["actor"]["phone"] == STUDENT_PHONE

    # Pagination + type filter
    r = await client.get(f"/teacher/courses/{course.id}/events?limit=1", headers=owner.headers())
    [first] = r.json()
    r = await client.get(f"/teacher/courses/{course.id}/events?before_id={first['id']}", headers=owner.headers())
    assert first["id"] not in [e["id"] for e in r.json()]
    r = await client.get(f"/teacher/courses/{course.id}/events?event_type=device_reset", headers=owner.headers())
    assert [e["event_type"] for e in r.json()] == ["device_reset"]

    # Another teacher cannot read this journal
    assert (await client.get(f"/teacher/courses/{course.id}/events", headers=other.headers())).status_code == 404
    other_events = (await client.get(f"/teacher/courses/{other_course.id}/events", headers=other.headers())).json()
    assert all(e["actor"] is None or e["actor"]["phone"] != STUDENT_PHONE for e in other_events)


# ---------- real client IP behind the panel (BFF) ----------


async def test_forwarded_ip_only_trusted_from_configured_proxy(client, db, monkeypatch):
    await register_student(client, STUDENT_PHONE)
    headers = {"X-Device-ID": new_device_id(), "X-Forwarded-For": "203.0.113.7"}
    body = {"phone": STUDENT_PHONE, "password": "wrong-pass"}

    await client.post("/auth/login", json=body, headers=headers)
    monkeypatch.setattr(get_settings(), "trusted_proxy_ips", "127.0.0.1")
    await client.post("/auth/login", json=body, headers=headers)

    ips = [e.ip for e in await audit_events(db, "login_failed")]
    assert ips == ["127.0.0.1", "203.0.113.7"]  # header ignored until the proxy is trusted


async def test_login_rate_limit_is_per_forwarded_ip(client, monkeypatch):
    from app.api.deps import login_rate_limiter

    monkeypatch.setattr(get_settings(), "trusted_proxy_ips", "127.0.0.1")
    login_rate_limiter.max_attempts = 2
    body = {"phone": STUDENT_PHONE, "password": PASSWORD}
    # Different teachers behind the same panel server must not block each other
    for n in range(3):
        r = await client.post(
            "/auth/login",
            json={**body, "phone": f"+99890777770{n}"},
            headers={"X-Device-ID": new_device_id(), "X-Forwarded-For": f"198.51.100.{n}"},
        )
        assert r.status_code == 401  # unknown user, but NOT 429


# ---------- CORS ----------


async def test_cors_only_for_configured_origin(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "cors_allowed_origins", "http://localhost:3000")
    preflight = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"}

    r = await client.options("/health", headers={"Origin": "http://localhost:3000", **preflight})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "access-control-allow-credentials" not in r.headers

    r = await client.options("/health", headers={"Origin": "https://evil.example", **preflight})
    assert "access-control-allow-origin" not in r.headers
    r = await client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


# ---------- mock video upload (dev) ----------


async def test_mock_upload_endpoint(client, db, monkeypatch):
    from app.main import app
    from app.services.video import get_video_provider

    dev_video = MockVideoProvider(auto_ready=True, upload_base_url="http://test/dev/mock-video-upload")
    app.dependency_overrides[get_video_provider] = lambda: dev_video
    teacher, tokens = await _teacher(client, db)
    course = await _course(client, tokens)
    lesson = (await client.post(f"/teacher/courses/{course['id']}/lessons", json={"title": "1"}, headers=tokens.headers())).json()

    upload = (await client.post(f"/teacher/lessons/{lesson['id']}/video-upload", headers=tokens.headers())).json()
    url = upload["upload_url"]
    assert url.startswith("http://test/dev/mock-video-upload/")
    video_id = upload["lesson"]["provider_video_id"]

    # Not uploaded yet -> sync keeps it "uploading"
    r = await client.post(f"/teacher/lessons/{lesson['id']}/sync-status", headers=tokens.headers())
    assert r.json()["status"] == "uploading"

    files = {"file": ("v.mp4", b"0" * 5000, "video/mp4")}
    assert (await client.post(url.replace("token=", "token=wrong"), data=upload["fields"], files=files)).status_code == 403
    r = await client.post(url, data=upload["fields"], files=files)
    assert r.status_code == 201 and r.json()["bytes"] > 5000
    assert dev_video.videos[video_id].status == LessonStatus.PROCESSING
    # One-time token
    assert (await client.post(url, data=upload["fields"], files=files)).status_code == 403

    r = await client.post(f"/teacher/lessons/{lesson['id']}/sync-status", headers=tokens.headers())
    assert r.json()["status"] == "ready"


async def test_mock_upload_endpoint_disabled_without_mock(client, video):
    # The default test provider has no upload_base_url -> endpoint is closed
    r = await client.post("/dev/mock-video-upload/anything?token=0123456789abc", content=b"x")
    assert r.status_code == 404


async def test_student_login_through_panel_device_needs_binding(client, db):
    """The panel rejects students: their login never returns tokens for an unbound device."""
    await register_student(client, STUDENT_PHONE)
    r = await login(client, STUDENT_PHONE, "panel-device-0001")
    assert r.json()["status"] == "device_binding_required"
