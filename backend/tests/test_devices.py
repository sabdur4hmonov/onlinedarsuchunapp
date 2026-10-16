from sqlalchemy import select

from app.models import Device
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

STUDENT_PHONE = "+998901111111"


async def test_first_login_requires_explicit_binding(client, db):
    student = await register_student(client, STUDENT_PHONE)
    device_id = new_device_id()

    r = await login(client, STUDENT_PHONE, device_id)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "device_binding_required"
    assert body["max_devices"] == 2
    assert "access_token" not in body
    # Nothing is bound automatically
    assert (await db.scalars(select(Device).where(Device.user_id == student["id"]))).all() == []

    r = await client.post(
        "/auth/devices/bind",
        json={"binding_token": body["binding_token"], "device_name": "Redmi Note", "platform": "android"},
        headers={"X-Device-ID": device_id},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert len(await audit_events(db, "device_bound")) == 1

    # Second login from the same, already bound device -> tokens straight away
    r = await login(client, STUDENT_PHONE, device_id)
    assert r.json()["status"] == "ok"


async def test_binding_token_cannot_be_used_from_another_device(client):
    await register_student(client, STUDENT_PHONE)
    r = await login(client, STUDENT_PHONE, new_device_id())
    token = r.json()["binding_token"]

    r = await client.post(
        "/auth/devices/bind",
        json={"binding_token": token, "device_name": "Other", "platform": "ios"},
        headers={"X-Device-ID": new_device_id()},
    )
    assert r.status_code == 401


async def test_login_from_third_device_is_rejected(client, db):
    await register_student(client, STUDENT_PHONE)
    await login_and_bind(client, STUDENT_PHONE)
    await login_and_bind(client, STUDENT_PHONE)

    r = await login(client, STUDENT_PHONE, new_device_id())
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "device_limit_reached"

    denied = await audit_events(db, "login_denied")
    assert len(denied) == 1
    assert denied[0].details["reason"] == "device_limit_reached"


async def test_binding_is_rechecked_against_limit(client):
    """A binding token taken while a slot was free must not bypass the limit later."""
    await register_student(client, STUDENT_PHONE)
    await login_and_bind(client, STUDENT_PHONE)  # 1 device bound

    third = new_device_id()
    stale_token = (await login(client, STUDENT_PHONE, third)).json()["binding_token"]
    await login_and_bind(client, STUDENT_PHONE)  # 2nd device fills the limit

    r = await client.post(
        "/auth/devices/bind",
        json={"binding_token": stale_token, "device_name": "Third", "platform": "android"},
        headers={"X-Device-ID": third},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "device_limit_reached"


async def test_teacher_reset_allows_binding_new_device(client, db):
    student = await register_student(client, STUDENT_PHONE)
    teacher = await create_teacher(db)
    await create_course_with_student(db, teacher, student["id"])

    old1 = await login_and_bind(client, STUDENT_PHONE)
    await login_and_bind(client, STUDENT_PHONE)
    assert (await login(client, STUDENT_PHONE, new_device_id())).status_code == 403

    teacher_tokens = await login_and_bind(client, teacher.phone)
    r = await client.post(f"/teacher/students/{student['id']}/devices/reset", json={}, headers=teacher_tokens.headers())
    assert r.status_code == 200, r.text
    assert len(r.json()["reset_devices"]) == 2

    reset_logs = await audit_events(db, "device_reset")
    assert len(reset_logs) == 1
    assert reset_logs[0].user_id == teacher.id
    assert reset_logs[0].details["student_id"] == student["id"]

    # Old device is unbound -> its token no longer works
    assert (await client.get("/auth/me", headers=old1.headers())).status_code == 401

    # A brand-new device can be bound now
    new = await login_and_bind(client, STUDENT_PHONE)
    assert (await client.get("/auth/me", headers=new.headers())).status_code == 200


async def test_teacher_can_reset_one_device(client, db):
    student = await register_student(client, STUDENT_PHONE)
    teacher = await create_teacher(db)
    await create_course_with_student(db, teacher, student["id"])
    first = await login_and_bind(client, STUDENT_PHONE)
    await login_and_bind(client, STUDENT_PHONE)

    teacher_tokens = await login_and_bind(client, teacher.phone)
    devices = (await client.get(f"/teacher/students/{student['id']}/devices", headers=teacher_tokens.headers())).json()
    target = next(d for d in devices if d["device_id"] == first.device_id)

    r = await client.post(
        f"/teacher/students/{student['id']}/devices/reset", json={"device_id": target["id"]}, headers=teacher_tokens.headers()
    )
    assert r.status_code == 200
    assert [d["device_id"] for d in r.json()["reset_devices"]] == [first.device_id]

    # One slot free again: the previously reset device itself can be re-bound
    again = await login_and_bind(client, STUDENT_PHONE, first.device_id)
    assert (await client.get("/auth/me", headers=again.headers())).status_code == 200


async def test_other_teacher_cannot_reset_devices(client, db):
    student = await register_student(client, STUDENT_PHONE)
    owner = await create_teacher(db, "+998900000001")
    stranger = await create_teacher(db, "+998900000002")
    await create_course_with_student(db, owner, student["id"])
    await login_and_bind(client, STUDENT_PHONE)

    stranger_tokens = await login_and_bind(client, stranger.phone)
    r = await client.post(f"/teacher/students/{student['id']}/devices/reset", json={}, headers=stranger_tokens.headers())
    assert r.status_code == 404
    assert await audit_events(db, "device_reset") == []


async def test_student_cannot_call_reset(client, db):
    student = await register_student(client, STUDENT_PHONE)
    tokens = await login_and_bind(client, STUDENT_PHONE)
    r = await client.post(f"/teacher/students/{student['id']}/devices/reset", json={}, headers=tokens.headers())
    assert r.status_code == 403


async def test_teacher_has_no_device_limit(client, db):
    teacher = await create_teacher(db)
    for _ in range(4):
        r = await login(client, teacher.phone, new_device_id())
        assert r.status_code == 200
        assert r.json()["status"] == "ok"  # never asks for binding
    assert (await db.scalars(select(Device).where(Device.user_id == teacher.id))).all() == []


async def test_wrong_password_is_rejected_and_logged(client, db):
    await register_student(client, STUDENT_PHONE)
    r = await client.post(
        "/auth/login", json={"phone": STUDENT_PHONE, "password": PASSWORD + "x"}, headers={"X-Device-ID": new_device_id()}
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "invalid_credentials"
    assert len(await audit_events(db, "login_failed")) == 1


async def test_login_rate_limit(client, db):
    from app.api.deps import login_rate_limiter

    login_rate_limiter.max_attempts = 5
    await register_student(client, STUDENT_PHONE)
    device_id = new_device_id()
    for _ in range(5):
        r = await client.post(
            "/auth/login", json={"phone": STUDENT_PHONE, "password": "wrong-pass"}, headers={"X-Device-ID": device_id}
        )
        assert r.status_code == 401
    r = await client.post("/auth/login", json={"phone": STUDENT_PHONE, "password": PASSWORD}, headers={"X-Device-ID": device_id})
    assert r.status_code == 429
    assert len(await audit_events(db, "login_rate_limited")) == 1
