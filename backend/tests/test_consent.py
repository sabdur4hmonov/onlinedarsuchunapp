from tests.conftest import audit_events, create_course_with_student, create_teacher, login_and_bind, register_student

STUDENT_PHONE = "+998903333333"


async def test_student_without_consent_cannot_open_content(client, db):
    student = await register_student(client, STUDENT_PHONE)
    teacher = await create_teacher(db)
    course = await create_course_with_student(db, teacher, student["id"])
    tokens = await login_and_bind(client, STUDENT_PHONE)
    url = f"/courses/{course.id}/content"

    # Course list is visible, content is not
    assert (await client.get("/courses/my", headers=tokens.headers())).status_code == 200
    r = await client.get(url, headers=tokens.headers())
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "consent_required"
    assert set(r.json()["detail"]["missing"]) == {"camera", "data_processing"}

    # Only one of the two is not enough
    assert (await client.post("/consents", json={"type": "camera"}, headers=tokens.headers())).status_code == 201
    r = await client.get(url, headers=tokens.headers())
    assert r.status_code == 403
    assert r.json()["detail"]["missing"] == ["data_processing"]

    assert (await client.post("/consents", json={"type": "data_processing"}, headers=tokens.headers())).status_code == 201
    r = await client.get(url, headers=tokens.headers())
    assert r.status_code == 200
    assert r.json()["course"]["id"] == str(course.id)
    assert len(await audit_events(db, "consent_granted")) == 2


async def test_consent_is_idempotent_and_parent_consent_type_exists(client):
    await register_student(client, STUDENT_PHONE)
    tokens = await login_and_bind(client, STUDENT_PHONE)
    for _ in range(2):
        r = await client.post("/consents", json={"type": "camera"}, headers=tokens.headers())
        assert r.status_code == 201
    r = await client.post("/consents", json={"type": "parent_consent"}, headers=tokens.headers())
    assert r.status_code == 201
    assert sorted(c["type"] for c in r.json()) == ["camera", "parent_consent"]


async def test_not_enrolled_student_gets_404_even_with_consent(client, db):
    other = await register_student(client, "+998904444444")
    teacher = await create_teacher(db)
    course = await create_course_with_student(db, teacher, other["id"])

    await register_student(client, STUDENT_PHONE)
    tokens = await login_and_bind(client, STUDENT_PHONE)
    for t in ("camera", "data_processing"):
        await client.post("/consents", json={"type": t}, headers=tokens.headers())
    assert (await client.get(f"/courses/{course.id}/content", headers=tokens.headers())).status_code == 404
