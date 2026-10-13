"""Phase 4 (evidence) and Phase 5 (human review) tests.

The central invariant under test:

    AI value = A, user edit = B  =>  the system must keep showing B,
    even after a fresh AI analysis.
"""

from __future__ import annotations

import uuid

from tests.helpers import make_txt, upload


def _analyzed_case(client, headers, case_id, text=None):
    """Upload + analyze one file, returning its evidence id."""
    data = make_txt(text or "劳动合同 甲方：某某科技有限公司 入职日期：2022年10月1日 月工资7500元")
    fid = upload(client, headers, case_id, "a.txt", data).json()["files"][0]["id"]
    assert client.post(f"/api/v1/files/{fid}/analyze", headers=headers).status_code == 200
    rows = client.get(f"/api/v1/cases/{case_id}/evidence", headers=headers).json()["evidence"]
    return rows[0]["id"], fid


# ---------- Phase 4: evidence ----------


def test_evidence_numbering_is_sequential_per_case(client, auth_headers, case_id):
    for i in range(4):
        upload(client, auth_headers, case_id, f"f{i}.txt", make_txt(f"文件{i} 内容"))
        client.post(f"/api/v1/cases/{case_id}/analyze", headers=auth_headers)

    rows = client.get(f"/api/v1/cases/{case_id}/evidence", headers=auth_headers).json()["evidence"]
    assert sorted(r["evidence_number"] for r in rows) == [1, 2, 3, 4]


def test_manual_evidence_gets_server_allocated_number(client, auth_headers, case_id):
    _analyzed_case(client, auth_headers, case_id)
    resp = client.post(
        f"/api/v1/cases/{case_id}/evidence",
        json={"title": "手写说明", "category": "other", "confirm_now": True},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["evidence_number"] == 2
    assert resp.json()["review_status"] == "CONFIRMED"


def test_evidence_confidence_below_threshold_is_pending(client, auth_headers, case_id):
    evidence_id, _ = _analyzed_case(client, auth_headers, case_id)
    row = client.get(f"/api/v1/evidence/{evidence_id}", headers=auth_headers).json()
    assert row["review_status"] == "PENDING"


def test_confirm_evidence(client, auth_headers, case_id):
    evidence_id, _ = _analyzed_case(client, auth_headers, case_id)
    resp = client.post(f"/api/v1/evidence/{evidence_id}/confirm", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["review_status"] == "CONFIRMED"


def test_evidence_requires_ownership(client, auth_headers, second_user_headers, case_id):
    evidence_id, fid = _analyzed_case(client, auth_headers, case_id)
    requests = (
        ("get", f"/api/v1/evidence/{evidence_id}", None),
        ("patch", f"/api/v1/evidence/{evidence_id}", {"title": "hacked"}),
        ("delete", f"/api/v1/evidence/{evidence_id}", None),
        ("post", f"/api/v1/evidence/{evidence_id}/confirm", None),
        ("get", f"/api/v1/cases/{case_id}/evidence", None),
    )
    for method, path, body in requests:
        call = getattr(client, method)
        resp = call(path, headers=second_user_headers, json=body) if body is not None else call(path, headers=second_user_headers)
        assert resp.status_code == 404, (method, path, resp.status_code)


# ---------- Phase 5: user edits are protected ----------


def test_user_edit_survives_reanalysis(client, auth_headers, case_id):
    """docs/12 Scenario 4: user edits the date -> re-analyze -> edit survives."""
    evidence_id, fid = _analyzed_case(client, auth_headers, case_id)

    edited = client.patch(
        f"/api/v1/evidence/{evidence_id}",
        json={"summary": "用户自己写的摘要", "proof_purpose": "用于证明用户主张的事实。"},
        headers=auth_headers,
    )
    assert edited.status_code == 200
    assert set(edited.json()["user_edited_fields"]) == {"summary", "proof_purpose"}

    # A fresh AI pass must not overwrite the human's values.
    reanalyzed = client.post(f"/api/v1/evidence/{evidence_id}/reanalyze", headers=auth_headers)
    assert reanalyzed.status_code == 200, reanalyzed.text

    body = reanalyzed.json()
    assert body["summary"] == "用户自己写的摘要"
    assert body["proof_purpose"] == "用于证明用户主张的事实。"
    assert set(body["user_edited_fields"]) == {"summary", "proof_purpose"}


def test_unedited_fields_are_still_refreshed_by_reanalysis(client, auth_headers, case_id):
    """Protected fields win; untouched fields still benefit from the new pass."""
    evidence_id, fid = _analyzed_case(client, auth_headers, case_id)
    client.patch(f"/api/v1/evidence/{evidence_id}", json={"summary": "我的摘要"}, headers=auth_headers)

    body = client.post(f"/api/v1/evidence/{evidence_id}/reanalyze", headers=auth_headers).json()
    assert body["summary"] == "我的摘要"  # protected
    assert body["proof_purpose"]  # untouched, so refreshed from AI


def test_review_queue_lists_low_confidence_items(client, auth_headers, case_id):
    _analyzed_case(client, auth_headers, case_id)
    items = client.get(f"/api/v1/cases/{case_id}/review-items", headers=auth_headers).json()
    assert items["total"] >= 1


def test_review_confirm_applies_user_value_over_ai(client, auth_headers, case_id):
    """Confirming a review item must store the user's value, not the AI's."""
    _analyzed_case(client, auth_headers, case_id)
    items = client.get(f"/api/v1/cases/{case_id}/review-items", headers=auth_headers).json()
    item = items["items"][0]

    patched = client.patch(
        f"/api/v1/review-items/{item['id']}",
        json={"user_value": {"summary": "人工核对后的摘要"}},
        headers=auth_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["user_value"] == {"summary": "人工核对后的摘要"}

    confirmed = client.post(f"/api/v1/review-items/{item['id']}/confirm", headers=auth_headers)
    assert confirmed.status_code == 200
    assert confirmed.json()["applied"]["summary"] == "人工核对后的摘要"

    # The entity now shows the human value.
    entity = client.get(f"/api/v1/evidence/{item['entity_id']}", headers=auth_headers).json()
    assert entity["summary"] == "人工核对后的摘要"
    assert "summary" in entity["user_edited_fields"]


def test_review_discard_keeps_item_out(client, auth_headers, case_id):
    _analyzed_case(client, auth_headers, case_id)
    item = client.get(f"/api/v1/cases/{case_id}/review-items", headers=auth_headers).json()["items"][0]
    resp = client.post(f"/api/v1/review-items/{item['id']}/discard", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "DISCARDED"

    pending = client.get(f"/api/v1/cases/{case_id}/review-items", headers=auth_headers).json()
    assert all(i["id"] != item["id"] for i in pending["items"])


def test_review_items_require_ownership(client, auth_headers, second_user_headers, case_id):
    _analyzed_case(client, auth_headers, case_id)
    item = client.get(f"/api/v1/cases/{case_id}/review-items", headers=auth_headers).json()["items"][0]
    assert (
        client.patch(
            f"/api/v1/review-items/{item['id']}",
            json={"user_value": {"summary": "x"}},
            headers=second_user_headers,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/review-items/{item['id']}/confirm", headers=second_user_headers
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/cases/{case_id}/review-items", headers=second_user_headers
        ).status_code
        == 404
    )
