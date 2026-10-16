import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Device
from tests.conftest import (
    audit_events,
    create_course_with_student,
    create_teacher,
    login,
    login_and_bind,
    new_device_id,
    register_student,
)

PHONE_A = "+998905555551"
PHONE_B = "+998905555552"


# ---------- A) one device = one student account ----------


async def test_device_bound_to_other_account_rejects_login(client, db):
    await register_student(client, PHONE_A)
    await register_student(client, PHONE_B)
    shared = await login_and_bind(client, PHONE_A)

    r = await login(client, PHONE_B, shared.device_id)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "device_already_bound_to_other_account"

    logs = await audit_events(db, "device_already_bound_to_other_account")
    assert len(logs) == 1
    assert logs[0].details["device_id"] == shared.device_id
    # Owner of the device is not affected
    assert (await client.get("/auth/me", headers=shared.headers())).status_code == 200


async def test_device_bound_to_other_account_rejects_bind(client, db):
    """B got a binding token while the device was still free, then A bound it first."""
    await register_student(client, PHONE_A)
    await register_student(client, PHONE_B)
    device_id = new_device_id()
    token_b = (await login(client, PHONE_B, device_id)).json()["binding_token"]

    await login_and_bind(client, PHONE_A, device_id)

    r = await client.post(
        "/auth/devices/bind",
        json={"binding_token": token_b, "device_name": "Shared", "platform": "android"},
        headers={"X-Device-ID": device_id},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "device_already_bound_to_other_account"
    assert len(await audit_events(db, "device_already_bound_to_other_account")) == 1


async def test_teacher_reset_frees_device_for_other_account(client, db):
    student_a = await register_student(client, PHONE_A)
    await register_student(client, PHONE_B)
    teacher = await create_teacher(db)
    await create_course_with_student(db, teacher, student_a["id"])
    shared = await login_and_bind(client, PHONE_A)
    assert (await login(client, PHONE_B, shared.device_id)).status_code == 409

    teacher_tokens = await login_and_bind(client, teacher.phone)
    r = await client.post(f"/teacher/students/{student_a['id']}/devices/reset", json={}, headers=teacher_tokens.headers())
    assert r.status_code == 200

    tokens_b = await login_and_bind(client, PHONE_B, shared.device_id)
    assert (await client.get("/auth/me", headers=tokens_b.headers())).status_code == 200


async def test_database_allows_only_one_active_binding_per_device(client, db):
    a = await register_student(client, PHONE_A)
    b = await register_student(client, PHONE_B)
    device_id = new_device_id()

    # An inactive (reset) row next to an active one is fine
    db.add(Device(user_id=uuid.UUID(a["id"]), device_id=device_id, device_name="x", platform="android", is_active=False))
    db.add(Device(user_id=uuid.UUID(b["id"]), device_id=device_id, device_name="x", platform="android", is_active=True))
    await db.commit()

    db.add(Device(user_id=uuid.UUID(a["id"]), device_id=device_id + "-2", device_name="x", platform="android"))
    db.add(Device(user_id=uuid.UUID(b["id"]), device_id=device_id + "-2", device_name="x", platform="android"))
    with pytest.raises(IntegrityError):
        await db.commit()


# ---------- B) refresh token reuse detection ----------


async def test_refresh_token_reuse_revokes_all_sessions(client, db):
    await register_student(client, PHONE_A)
    tokens = await login_and_bind(client, PHONE_A)
    headers = {"X-Device-ID": tokens.device_id}

    r = await client.post("/auth/refresh", json={"refresh_token": tokens.refresh}, headers=headers)
    assert r.status_code == 200
    fresh = r.json()

    # The old (already rotated) token comes back -> theft signal
    r = await client.post("/auth/refresh", json={"refresh_token": tokens.refresh}, headers=headers)
    assert r.status_code == 401

    # Everything of this user is dead now, including the freshly issued pair
    assert (await client.post("/auth/refresh", json={"refresh_token": fresh["refresh_token"]}, headers=headers)).status_code == 401
    r = await client.get("/auth/me", headers={"Authorization": f"Bearer {fresh['access_token']}", **headers})
    assert r.status_code == 401

    logs = await audit_events(db, "refresh_token_reuse_detected")
    assert len(logs) == 1
    assert len(logs[0].details["revoked_session_ids"]) == 1


async def test_refresh_token_reuse_revokes_sessions_on_every_device(client, db):
    """Teachers may have several sessions at once — reuse must kill all of them."""
    teacher = await create_teacher(db)
    laptop = await login_and_bind(client, teacher.phone)
    phone = await login_and_bind(client, teacher.phone)

    r = await client.post("/auth/refresh", json={"refresh_token": laptop.refresh}, headers={"X-Device-ID": laptop.device_id})
    assert r.status_code == 200
    r = await client.post("/auth/refresh", json={"refresh_token": laptop.refresh}, headers={"X-Device-ID": laptop.device_id})
    assert r.status_code == 401

    assert (await client.get("/auth/me", headers=phone.headers())).status_code == 401
    logs = await audit_events(db, "refresh_token_reuse_detected")
    assert len(logs) == 1
    assert len(logs[0].details["revoked_session_ids"]) == 2


async def test_unknown_refresh_token_does_not_trigger_reuse(client, db):
    await register_student(client, PHONE_A)
    tokens = await login_and_bind(client, PHONE_A)
    r = await client.post("/auth/refresh", json={"refresh_token": "made-up-token"}, headers={"X-Device-ID": tokens.device_id})
    assert r.status_code == 401
    assert await audit_events(db, "refresh_token_reuse_detected") == []
    assert (await client.get("/auth/me", headers=tokens.headers())).status_code == 200
