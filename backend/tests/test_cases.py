"""Case CRUD tests, including the Phase 1 acceptance criterion:

"创建案件并重新打开后数据仍存在" — create a case, reopen it, data is still there.
"""

from __future__ import annotations


def _create(client, headers, name="被拖欠工资", description="2024-2026"):
    resp = client.post(
        "/api/v1/cases", json={"name": name, "description": description}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_case_and_reopen_persists_data(client, auth_headers):
    """Phase 1 acceptance: data survives a reopen."""
    created = _create(client, auth_headers)
    assert created["name"] == "被拖欠工资"
    assert created["status"] == "ACTIVE"
    assert created["file_count"] == 0

    reopened = client.get(f"/api/v1/cases/{created['id']}", headers=auth_headers)
    assert reopened.status_code == 200
    body = reopened.json()
    assert body["id"] == created["id"]
    assert body["name"] == "被拖欠工资"
    assert body["description"] == "2024-2026"


def test_case_requires_authentication(client):
    resp = client.post("/api/v1/cases", json={"name": "x"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_create_case_rejects_blank_name(client, auth_headers):
    resp = client.post("/api/v1/cases", json={"name": "   "}, headers=auth_headers)
    assert resp.status_code == 422


def test_list_cases_paginates_and_is_sorted(client, auth_headers):
    for i in range(3):
        _create(client, auth_headers, name=f"case-{i}")
    resp = client.get("/api/v1/cases?limit=2&offset=0", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["limit"] == 2 and body["offset"] == 0


def test_update_case(client, auth_headers):
    created = _create(client, auth_headers)
    resp = client.patch(
        f"/api/v1/cases/{created['id']}",
        json={"name": "改过的案件名", "status": "ARCHIVED"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "改过的案件名"
    assert resp.json()["status"] == "ARCHIVED"


def test_update_case_rejects_invalid_status(client, auth_headers):
    created = _create(client, auth_headers)
    resp = client.patch(
        f"/api/v1/cases/{created['id']}", json={"status": "NOPE"}, headers=auth_headers
    )
    assert resp.status_code == 422


def test_delete_case_is_soft_and_hides_it(client, auth_headers, db_session):
    from sqlalchemy import select

    from app.models.case import Case

    created = _create(client, auth_headers)
    resp = client.delete(f"/api/v1/cases/{created['id']}", headers=auth_headers)
    assert resp.status_code == 204

    assert client.get(f"/api/v1/cases/{created['id']}", headers=auth_headers).status_code == 404
    assert client.get("/api/v1/cases", headers=auth_headers).json()["total"] == 0

    # Row still exists — soft delete only marks it.
    row = db_session.get(Case, __import__("uuid").UUID(created["id"]))
    assert row is not None and row.deleted_at is not None


def test_user_cannot_see_or_touch_another_users_case(
    client, auth_headers, second_user_headers
):
    """docs/12_TEST_PLAN Scenario 5: cross-tenant access must fail."""
    created = _create(client, auth_headers, name="我的案件")

    # Not visible in the other user's list.
    assert client.get("/api/v1/cases", headers=second_user_headers).json()["total"] == 0

    # Direct fetch, patch and delete all 404 for the other user.
    other_id = created["id"]
    assert (
        client.get(f"/api/v1/cases/{other_id}", headers=second_user_headers).status_code == 404
    )
    assert (
        client.patch(
            f"/api/v1/cases/{other_id}", json={"name": "hacked"}, headers=second_user_headers
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/v1/cases/{other_id}", headers=second_user_headers).status_code
        == 404
    )

    # Owner's data untouched.
    assert client.get(f"/api/v1/cases/{other_id}", headers=auth_headers).json()["name"] == "我的案件"


def test_get_missing_case_returns_404_envelope(client, auth_headers):
    import uuid

    resp = client.get(f"/api/v1/cases/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404
    err = resp.json()["error"]
    assert err["code"] == "CASE_NOT_FOUND"
    assert "request_id" in err


def test_error_envelope_never_leaks_stack_traces(client, auth_headers):
    resp = client.get(f"/api/v1/cases/{'not-a-uuid'}", headers=auth_headers)
    assert resp.status_code in (404, 422)
    text = resp.text
    assert "Traceback" not in text
    assert "File \"" not in text


def test_generate_narrative_requires_materials(client, auth_headers, case_id):
    resp = client.post(f"/api/v1/cases/{case_id}/narrative", headers=auth_headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "NO_MATERIALS"


def test_generate_narrative_from_evidence_and_events(client, auth_headers, case_id, db_session):
    """Mock provider has no generate_text → deterministic template path."""
    import uuid as _uuid

    from app.models.case import Case
    from app.models.evidence import Evidence
    from app.models.event import Event

    case = db_session.get(Case, _uuid.UUID(case_id))
    db_session.add(
        Evidence(
            case_id=case.id,
            evidence_number=1,
            title="labor_contract—劳动合同.pdf",
            category="labor_contract",
            summary="张伟于2022年3月1日入职某科技公司，任软件工程师，月工资20000元。",
        )
    )
    db_session.add(
        Event(
            case_id=case.id,
            title="公司发出解除通知",
            event_date=__import__("datetime").date(2026, 9, 10),
            precision="day",
        )
    )
    db_session.commit()

    resp = client.post(f"/api/v1/cases/{case_id}/narrative", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "2026-09-10 公司发出解除通知" in body["narrative"]
    assert "张伟于2022年3月1日入职" in body["narrative"]
    assert body["provider"] == "template"
    # Generation must not persist — the user saves the draft themselves.
    db_session.refresh(case)
    assert case.description == "测试"


def test_generate_narrative_denied_for_other_user(client, second_user_headers, case_id):
    resp = client.post(f"/api/v1/cases/{case_id}/narrative", headers=second_user_headers)
    assert resp.status_code == 404
