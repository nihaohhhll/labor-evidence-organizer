"""Workbench phase: claims CRUD, progress, trial prep, case audit."""

from __future__ import annotations

from tests.helpers import make_txt, upload


def _add_claim(client, headers, case_id, **extra):
    body = {"title": "请求支付违法解除赔偿金"}
    body.update(extra)
    resp = client.post(f"/api/v1/cases/{case_id}/claims", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _confirmed_evidence_ids(client, headers, case_id, count=1):
    ids = []
    for i in range(count):
        data = make_txt(
            f"劳动合同 甲方：某某科技有限公司 入职日期：2022年10月{i + 1}日 月工资7500元"
        )
        fid = upload(client, headers, case_id, f"doc{i}.txt", data).json()["files"][0]["id"]
        client.post(f"/api/v1/files/{fid}/analyze", headers=headers)
    rows = client.get(f"/api/v1/cases/{case_id}/evidence", headers=headers).json()["evidence"]
    for row in rows:
        client.post(f"/api/v1/evidence/{row['id']}/confirm", headers=headers)
    return [r["id"] for r in rows]


def test_claim_crud_roundtrip(client, auth_headers, case_id):
    claim = _add_claim(
        client,
        auth_headers,
        case_id,
        description="违法解除劳动合同",
        amount="15000 元",
        calculation="7500 × 2 个月赔偿金",
        notes="口头通知解除",
    )
    assert claim["status"] == "DRAFT"
    assert claim["amount"] == "15000 元"

    resp = client.get(f"/api/v1/cases/{case_id}/claims", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    resp = client.patch(
        f"/api/v1/claims/{claim['id']}",
        json={"status": "CONFIRMED", "amount": "15000.00 元"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "CONFIRMED"
    assert resp.json()["amount"] == "15000.00 元"

    resp = client.delete(f"/api/v1/claims/{claim['id']}", headers=auth_headers)
    assert resp.status_code == 204
    assert client.get(f"/api/v1/cases/{case_id}/claims", headers=auth_headers).json()["total"] == 0


def test_claim_links_evidence_and_events(client, auth_headers, case_id):
    ev_ids = _confirmed_evidence_ids(client, auth_headers, case_id, count=1)
    events = client.post(
        f"/api/v1/cases/{case_id}/events/build", headers=auth_headers
    ).json()["events"]
    assert events
    claim = _add_claim(
        client, auth_headers, case_id, evidence_ids=ev_ids, event_ids=[events[0]["id"]]
    )
    assert claim["evidence_ids"] == ev_ids
    assert claim["event_ids"] == [events[0]["id"]]

    resp = client.patch(
        f"/api/v1/claims/{claim['id']}",
        json={"evidence_ids": [], "event_ids": []},
        headers=auth_headers,
    )
    assert resp.json()["evidence_ids"] == []
    assert resp.json()["event_ids"] == []


def test_claim_link_rejects_foreign_case(client, auth_headers, case_id, second_user_headers):
    other = client.post(
        "/api/v1/cases", json={"name": "别人的案件"}, headers=second_user_headers
    ).json()
    claim = _add_claim(client, auth_headers, case_id)
    resp = client.patch(
        f"/api/v1/claims/{claim['id']}",
        json={"evidence_ids": ["00000000-0000-0000-0000-000000000001"]},
        headers=auth_headers,
    )
    assert resp.status_code == 404
    resp = client.get(f"/api/v1/cases/{other['id']}/claims", headers=auth_headers)
    assert resp.status_code == 404


def test_claim_ownership_is_enforced(client, auth_headers, case_id, second_user_headers):
    claim = _add_claim(client, auth_headers, case_id)
    resp = client.get(f"/api/v1/claims/{claim['id']}", headers=second_user_headers)
    assert resp.status_code == 404
    resp = client.delete(f"/api/v1/claims/{claim['id']}", headers=second_user_headers)
    assert resp.status_code == 404


def test_blank_claim_title_rejected(client, auth_headers, case_id):
    resp = client.post(
        f"/api/v1/cases/{case_id}/claims", json={"title": "   "}, headers=auth_headers
    )
    assert resp.status_code == 422


def test_progress_empty_case(client, auth_headers, case_id):
    resp = client.get(f"/api/v1/cases/{case_id}/progress", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["stage"] == 0
    assert data["stage_label"] == "案件初始化"
    assert data["counts"]["files_total"] == 0
    # First undone task is upload.
    undone = [t for t in data["tasks"] if not t["done"]]
    assert undone[0]["id"] == "upload_files"
    assert data["next_action_href"] == "/files"


def test_progress_advances_with_real_work(client, auth_headers, case_id):
    # After upload + analyze: stage moves off 0.
    data = make_txt("劳动合同 甲方：某某科技有限公司 入职日期：2022年10月1日 月工资7500元")
    fid = upload(client, auth_headers, case_id, "a.txt", data).json()["files"][0]["id"]
    client.post(f"/api/v1/files/{fid}/analyze", headers=auth_headers)
    prog = client.get(f"/api/v1/cases/{case_id}/progress", headers=auth_headers).json()
    assert prog["stage"] >= 1
    assert prog["counts"]["evidence_total"] >= 1
    assert prog["counts"]["review_pending"] >= 1
    # upload task done
    tasks = {t["id"]: t for t in prog["tasks"]}
    assert tasks["upload_files"]["done"] is True


def test_progress_archived_case(client, auth_headers, case_id):
    resp = client.patch(
        f"/api/v1/cases/{case_id}", json={"status": "ARCHIVED"}, headers=auth_headers
    )
    assert resp.status_code == 200
    prog = client.get(f"/api/v1/cases/{case_id}/progress", headers=auth_headers).json()
    assert prog["stage"] == 7
    assert prog["stage_label"] == "案件归档"
    assert {t["id"]: t["done"] for t in prog["tasks"]}["archive"] is True


def test_trial_prep_roundtrip(client, auth_headers, case_id):
    resp = client.get(f"/api/v1/cases/{case_id}/trial-prep", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["checklist"] == {}

    resp = client.patch(
        f"/api/v1/cases/{case_id}/trial-prep",
        json={
            "hearing_date": "2026-11-20",
            "hearing_note": "第一仲裁庭",
            "checklist": {"originals_safe": True, "id_document": True},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["hearing_date"] == "2026-11-20"
    assert data["checklist"]["originals_safe"] is True

    # Unknown checklist keys are ignored, known ones persist.
    resp = client.patch(
        f"/api/v1/cases/{case_id}/trial-prep",
        json={"checklist": {"bogus": True, "copies_printed": True}},
        headers=auth_headers,
    )
    data = resp.json()
    assert "bogus" not in data["checklist"]
    assert data["checklist"]["originals_safe"] is True
    assert data["checklist"]["copies_printed"] is True

    # Case detail carries the same working copy.
    detail = client.get(f"/api/v1/cases/{case_id}", headers=auth_headers).json()
    assert detail["trial_prep"]["hearing_date"] == "2026-11-20"


def test_trial_prep_ownership(client, auth_headers, case_id, second_user_headers):
    resp = client.get(f"/api/v1/cases/{case_id}/trial-prep", headers=second_user_headers)
    assert resp.status_code == 404


def test_case_audit_lists_recent_actions(client, auth_headers, case_id):
    _add_claim(client, auth_headers, case_id)
    resp = client.get(f"/api/v1/cases/{case_id}/audit", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    actions = [i["action"] for i in resp.json()["items"]]
    assert "case.created" in actions
    assert "claim.created" in actions
    assert resp.json()["total"] >= 2


def test_case_audit_ownership(client, auth_headers, case_id, second_user_headers):
    resp = client.get(f"/api/v1/cases/{case_id}/audit", headers=second_user_headers)
    assert resp.status_code == 404


def test_derive_progress_all_files_failed_stays_collecting():
    from app.services.workbench import derive_progress

    counts = {
        "files_total": 2,
        "files_ready": 0,
        "files_processing": 0,
        "files_failed": 2,
        "evidence_total": 0,
    }
    out = derive_progress(counts, case_status="ACTIVE", trial_prep=None)
    assert out["stage"] == 1
    assert out["stage_label"] == "材料收集"


def test_trial_prep_complete_requires_all_items():
    from app.services.workbench import TRIAL_CHECKLIST, trial_prep_complete

    assert trial_prep_complete(None) is False
    full = {item_id: True for item_id, _ in TRIAL_CHECKLIST}
    assert trial_prep_complete({"checklist": full}) is True
    full["originals_safe"] = False
    assert trial_prep_complete({"checklist": full}) is False
