from tests.conftest import audit_events, login_and_bind, new_device_id, register_student

STUDENT_PHONE = "+998902222222"


async def test_new_login_revokes_previous_session(client, db):
    await register_student(client, STUDENT_PHONE)
    first = await login_and_bind(client, STUDENT_PHONE)
    assert (await client.get("/auth/me", headers=first.headers())).status_code == 200

    second = await login_and_bind(client, STUDENT_PHONE)  # login from another device

    # Old session is dead immediately: access token AND refresh token
    assert (await client.get("/auth/me", headers=first.headers())).status_code == 401
    r = await client.post("/auth/refresh", json={"refresh_token": first.refresh}, headers={"X-Device-ID": first.device_id})
    assert r.status_code == 401
    # New session works
    assert (await client.get("/auth/me", headers=second.headers())).status_code == 200

    revoked = await audit_events(db, "session_revoked")
    assert any(log.details["reason"] == "new_login" for log in revoked)


async def test_relogin_on_same_device_also_keeps_single_session(client):
    await register_student(client, STUDENT_PHONE)
    device_id = new_device_id()
    first = await login_and_bind(client, STUDENT_PHONE, device_id)
    second = await login_and_bind(client, STUDENT_PHONE, device_id)

    assert (await client.get("/auth/me", headers=first.headers())).status_code == 401
    assert (await client.get("/auth/me", headers=second.headers())).status_code == 200


async def test_revoked_refresh_token_does_not_work(client):
    await register_student(client, STUDENT_PHONE)
    tokens = await login_and_bind(client, STUDENT_PHONE)

    assert (await client.post("/auth/logout", headers=tokens.headers())).status_code == 204

    r = await client.post("/auth/refresh", json={"refresh_token": tokens.refresh}, headers={"X-Device-ID": tokens.device_id})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "invalid_refresh_token"
    assert (await client.get("/auth/me", headers=tokens.headers())).status_code == 401


async def test_refresh_rotation_invalidates_old_refresh_token(client):
    await register_student(client, STUDENT_PHONE)
    tokens = await login_and_bind(client, STUDENT_PHONE)
    headers = {"X-Device-ID": tokens.device_id}

    r = await client.post("/auth/refresh", json={"refresh_token": tokens.refresh}, headers=headers)
    assert r.status_code == 200
    new_refresh = r.json()["refresh_token"]
    assert new_refresh != tokens.refresh

    # New one works
    assert (await client.post("/auth/refresh", json={"refresh_token": new_refresh}, headers=headers)).status_code == 200
    # Old one is used up (sending it again also triggers reuse detection, see test_security_fixes.py)
    assert (await client.post("/auth/refresh", json={"refresh_token": tokens.refresh}, headers=headers)).status_code == 401


async def test_token_with_other_device_id_is_rejected(client):
    await register_student(client, STUDENT_PHONE)
    tokens = await login_and_bind(client, STUDENT_PHONE)
    other_device = new_device_id()

    r = await client.get("/auth/me", headers={"Authorization": f"Bearer {tokens.access}", "X-Device-ID": other_device})
    assert r.status_code == 401
    # Missing header is rejected too
    assert (await client.get("/auth/me", headers={"Authorization": f"Bearer {tokens.access}"})).status_code == 401
    # Refresh token can't be moved to another device either
    r = await client.post("/auth/refresh", json={"refresh_token": tokens.refresh}, headers={"X-Device-ID": other_device})
    assert r.status_code == 401


async def test_garbage_token_is_rejected(client):
    r = await client.get("/auth/me", headers={"Authorization": "Bearer not-a-jwt", "X-Device-ID": new_device_id()})
    assert r.status_code == 401
