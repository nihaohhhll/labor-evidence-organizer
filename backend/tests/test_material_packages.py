"""Phase 9-A: arbitration material package base layer.

Covers the twelve cases required by the task spec:

1. normal create; 2. add/sort/update items; 3. cross-case evidence rejected;
4. non-existent evidence rejected; 5. unauthorized access rejected;
6. snapshot create + history read; 7. draft edits never rewrite history;
8. concurrent save/version conflict; 9. duplicate submits stay safe;
10. empty package & invalid item edges; 11. migration check (run via
`alembic check` in the verification step, metadata parity asserted here);
12. A1/A2/A3 regression is covered by the untouched existing suite.
"""

from __future__ import annotations

import uuid


def _err_code(resp) -> str:
    """The app wraps errors in {"error": {"code", ...}} (app/main.py)."""
    return resp.json()["error"]["code"]


def _mk_evidence(client, headers, case_id, title="工资条", proof=None):
    """Manual evidence row — no analysis needed, deterministic and fast."""
    body = {"title": title, "category": "wage", "confirm_now": True}
    if proof is not None:
        body["proof_purpose"] = proof
    resp = client.post(f"/api/v1/cases/{case_id}/evidence", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _mk_package(client, headers, case_id, name="仲裁材料包"):
    resp = client.post(
        f"/api/v1/cases/{case_id}/material-packages",
        json={"name": name},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _save(client, headers, pkg_id, expected_version, items):
    return client.put(
        f"/api/v1/material-packages/{pkg_id}/items",
        json={"expected_draft_version": expected_version, "items": items},
        headers=headers,
    )


def _snapshot(client, headers, pkg_id, expected_version):
    return client.post(
        f"/api/v1/material-packages/{pkg_id}/snapshots",
        json={"expected_draft_version": expected_version},
        headers=headers,
    )


# ---------- 1. create ----------


def test_create_package(client, auth_headers, case_id):
    pkg = _mk_package(client, auth_headers, case_id)
    assert pkg["status"] == "DRAFT"
    assert pkg["draft_version"] == 1
    assert pkg["item_count"] == 0
    assert pkg["snapshot_count"] == 0
    assert pkg["items"] == []


def test_create_package_in_other_users_case_is_404(
    client, auth_headers, second_user_headers, case_id
):
    resp = client.post(
        f"/api/v1/cases/{case_id}/material-packages",
        json={"name": "x"},
        headers=second_user_headers,
    )
    assert resp.status_code == 404
    assert _err_code(resp) == "CASE_NOT_FOUND"


def test_create_package_empty_name_is_422(client, auth_headers, case_id):
    resp = client.post(
        f"/api/v1/cases/{case_id}/material-packages",
        json={"name": "   "},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_list_packages_counts(client, auth_headers, case_id):
    _mk_package(client, auth_headers, case_id, "包A")
    _mk_package(client, auth_headers, case_id, "包B")
    body = client.get(
        f"/api/v1/cases/{case_id}/material-packages", headers=auth_headers
    ).json()
    assert body["total"] == 2
    assert len(body["items"]) == 2


# ---------- 2. items: add / sort / update ----------


def test_save_items_assigns_order_and_numbers_from_payload(
    client, auth_headers, case_id
):
    e1 = _mk_evidence(client, auth_headers, case_id, "劳动合同")
    e2 = _mk_evidence(client, auth_headers, case_id, "工资条")
    e3 = _mk_evidence(client, auth_headers, case_id, "考勤记录")
    pkg = _mk_package(client, auth_headers, case_id)

    # Deliberately scrambled payload order: numbering must follow payload,
    # never database row order (business rule 3).
    resp = _save(
        client,
        auth_headers,
        pkg["id"],
        1,
        [
            {"evidence_id": e3},
            {"evidence_id": e1, "display_name": "劳动合同（2022）", "proof_purpose": "证明劳动关系"},
            {"evidence_id": e2, "review_status": "APPROVED"},
        ],
    )
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    assert detail["draft_version"] == 2
    assert detail["item_count"] == 3
    orders = [(i["item_order"], i["display_number"], i["evidence_id"]) for i in detail["items"]]
    assert orders == [(1, 1, e3), (2, 2, e1), (3, 3, e2)]
    # display_name defaults to the evidence title when omitted
    assert detail["items"][0]["display_name"] == "考勤记录"
    assert detail["items"][1]["display_name"] == "劳动合同（2022）"
    assert detail["items"][1]["proof_purpose"] == "证明劳动关系"
    # proof_purpose defaults from the evidence row when omitted
    assert detail["items"][2]["proof_purpose"] is None
    assert detail["items"][2]["review_status"] == "APPROVED"
    assert detail["items"][0]["review_status"] == "PENDING"
    # evidence_number is projected from the source evidence
    assert detail["items"][1]["evidence_number"] >= 1


def test_reorder_and_remove_keeps_item_ids_stable(client, auth_headers, case_id):
    e1 = _mk_evidence(client, auth_headers, case_id, "A")
    e2 = _mk_evidence(client, auth_headers, case_id, "B")
    e3 = _mk_evidence(client, auth_headers, case_id, "C")
    pkg = _mk_package(client, auth_headers, case_id)
    first = _save(
        client,
        auth_headers,
        pkg["id"],
        1,
        [{"evidence_id": e1}, {"evidence_id": e2}, {"evidence_id": e3}],
    ).json()
    ids_by_evidence = {i["evidence_id"]: i["id"] for i in first["items"]}

    # Swap first two, drop the third.
    resp = _save(
        client,
        auth_headers,
        pkg["id"],
        first["draft_version"],
        [{"evidence_id": e2}, {"evidence_id": e1, "display_name": "改名"}],
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert [(i["item_order"], i["evidence_id"]) for i in items] == [(1, e2), (2, e1)]
    assert [i["display_number"] for i in items] == [1, 2]
    # kept rows keep their primary keys (no delete + reinsert)
    assert items[0]["id"] == ids_by_evidence[e2]
    assert items[1]["id"] == ids_by_evidence[e1]
    assert items[1]["display_name"] == "改名"
    assert resp.json()["item_count"] == 2


def test_save_empty_items_clears_draft(client, auth_headers, case_id):
    e1 = _mk_evidence(client, auth_headers, case_id, "A")
    pkg = _mk_package(client, auth_headers, case_id)
    _save(client, auth_headers, pkg["id"], 1, [{"evidence_id": e1}])
    resp = _save(client, auth_headers, pkg["id"], 2, [])
    assert resp.status_code == 200
    assert resp.json()["item_count"] == 0
    assert resp.json()["items"] == []


# ---------- 3 + 4. bad evidence references ----------


def test_reject_cross_case_and_missing_evidence_with_same_code(
    client, auth_headers, second_user_headers, case_id
):
    # Second user's evidence lives in a different case entirely.
    resp = client.post(
        "/api/v1/cases", json={"name": "别人的案件"}, headers=second_user_headers
    )
    other_case = resp.json()["id"]
    foreign = _mk_evidence(client, second_user_headers, other_case, "别人的证据")
    missing = str(uuid.uuid4())

    pkg = _mk_package(client, auth_headers, case_id)
    for bad_id in (foreign, missing):
        resp = _save(
            client, auth_headers, pkg["id"], 1, [{"evidence_id": bad_id}]
        )
        assert resp.status_code == 400
        # Identical code for cross-case and non-existent: the API must not
        # confirm whether a guessed id exists anywhere.
        assert _err_code(resp) == "EVIDENCE_NOT_FOUND"


def test_duplicate_evidence_in_payload_rejected(client, auth_headers, case_id):
    e1 = _mk_evidence(client, auth_headers, case_id, "A")
    pkg = _mk_package(client, auth_headers, case_id)
    resp = _save(
        client, auth_headers, pkg["id"], 1, [{"evidence_id": e1}, {"evidence_id": e1}]
    )
    assert resp.status_code == 400
    assert _err_code(resp) == "DUPLICATE_EVIDENCE"


def test_invalid_review_status_is_422(client, auth_headers, case_id):
    e1 = _mk_evidence(client, auth_headers, case_id, "A")
    pkg = _mk_package(client, auth_headers, case_id)
    resp = _save(
        client,
        auth_headers,
        pkg["id"],
        1,
        [{"evidence_id": e1, "review_status": "WHATEVER"}],
    )
    assert resp.status_code == 422


# ---------- 5. ownership ----------


def test_all_endpoints_404_for_other_user(client, auth_headers, second_user_headers, case_id):
    e1 = _mk_evidence(client, auth_headers, case_id, "A")
    pkg = _mk_package(client, auth_headers, case_id)
    _save(client, auth_headers, pkg["id"], 1, [{"evidence_id": e1}])
    _snapshot(client, auth_headers, pkg["id"], 2)

    pid = pkg["id"]
    calls = [
        ("get", f"/api/v1/material-packages/{pid}", None),
        ("patch", f"/api/v1/material-packages/{pid}", {"name": "hack"}),
        ("delete", f"/api/v1/material-packages/{pid}", None),
        ("get", f"/api/v1/material-packages/{pid}/items", None),
        ("put", f"/api/v1/material-packages/{pid}/items", {"expected_draft_version": 1, "items": []}),
        ("post", f"/api/v1/material-packages/{pid}/snapshots", {"expected_draft_version": 2}),
        ("get", f"/api/v1/material-packages/{pid}/snapshots", None),
        ("get", f"/api/v1/material-packages/{pid}/snapshots/1", None),
        ("get", f"/api/v1/cases/{case_id}/material-packages", None),
    ]
    for method, path, body in calls:
        call = getattr(client, method)
        resp = (
            call(path, json=body, headers=second_user_headers)
            if body is not None
            else call(path, headers=second_user_headers)
        )
        assert resp.status_code == 404, (method, path, resp.status_code, resp.text)


def test_unauthenticated_requests_are_401(client, auth_headers, case_id):
    pkg = _mk_package(client, auth_headers, case_id)
    resp = client.get(f"/api/v1/material-packages/{pkg['id']}")
    assert resp.status_code == 401


# ---------- 6 + 7. snapshots ----------


def test_snapshot_create_and_read_history(client, auth_headers, case_id):
    e1 = _mk_evidence(client, auth_headers, case_id, "劳动合同", proof="证明劳动关系存续")
    e2 = _mk_evidence(client, auth_headers, case_id, "工资条")
    pkg = _mk_package(client, auth_headers, case_id)
    _save(
        client,
        auth_headers,
        pkg["id"],
        1,
        [
            {"evidence_id": e1, "display_name": "证据一：劳动合同"},
            {"evidence_id": e2, "review_status": "APPROVED"},
        ],
    )

    resp = _snapshot(client, auth_headers, pkg["id"], 2)
    assert resp.status_code == 201, resp.text
    snap = resp.json()
    assert snap["version"] == 1
    assert snap["draft_version_captured"] == 2

    history = client.get(
        f"/api/v1/material-packages/{pkg['id']}/snapshots", headers=auth_headers
    ).json()
    assert history["total"] == 1

    read = client.get(
        f"/api/v1/material-packages/{pkg['id']}/snapshots/1", headers=auth_headers
    ).json()
    content = read["content"]
    stored = content["items"]
    assert [i["display_number"] for i in stored] == [1, 2]
    assert stored[0]["display_name"] == "证据一：劳动合同"
    assert stored[0]["proof_purpose"] == "证明劳动关系存续"
    assert stored[1]["review_status"] == "APPROVED"
    # per-item source state is computed at read time
    assert all(i["source_status"] == "OK" for i in stored)


def test_snapshot_immutable_when_draft_changes(client, auth_headers, case_id):
    e1 = _mk_evidence(client, auth_headers, case_id, "A")
    e2 = _mk_evidence(client, auth_headers, case_id, "B")
    e3 = _mk_evidence(client, auth_headers, case_id, "C")
    pkg = _mk_package(client, auth_headers, case_id)
    _save(client, auth_headers, pkg["id"], 1, [{"evidence_id": e1}, {"evidence_id": e2}])
    assert _snapshot(client, auth_headers, pkg["id"], 2).status_code == 201

    # Mutate the draft: rename, drop one item, add another.
    _save(
        client,
        auth_headers,
        pkg["id"],
        2,
        [{"evidence_id": e1, "display_name": "改过的名字"}, {"evidence_id": e3}],
    )
    assert _snapshot(client, auth_headers, pkg["id"], 3).status_code == 201

    v1 = client.get(
        f"/api/v1/material-packages/{pkg['id']}/snapshots/1", headers=auth_headers
    ).json()["content"]["items"]
    assert [(i["evidence_id"], i["display_name"]) for i in v1] == [
        (e1, "A"),
        (e2, "B"),
    ]
    v2 = client.get(
        f"/api/v1/material-packages/{pkg['id']}/snapshots/2", headers=auth_headers
    ).json()["content"]["items"]
    assert [(i["evidence_id"], i["display_name"]) for i in v2] == [
        (e1, "改过的名字"),
        (e3, "C"),
    ]


def test_snapshot_reports_deleted_and_changed_sources(client, auth_headers, case_id):
    e1 = _mk_evidence(client, auth_headers, case_id, "保持不变")
    e2 = _mk_evidence(client, auth_headers, case_id, "将被删除")
    e3 = _mk_evidence(client, auth_headers, case_id, "将被修改")
    pkg = _mk_package(client, auth_headers, case_id)
    _save(
        client,
        auth_headers,
        pkg["id"],
        1,
        [{"evidence_id": e1}, {"evidence_id": e2}, {"evidence_id": e3}],
    )
    assert _snapshot(client, auth_headers, pkg["id"], 2).status_code == 201

    assert client.delete(f"/api/v1/evidence/{e2}", headers=auth_headers).status_code == 204
    resp = client.patch(
        f"/api/v1/evidence/{e3}",
        json={"title": "标题改了"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    items = client.get(
        f"/api/v1/material-packages/{pkg['id']}/snapshots/1", headers=auth_headers
    ).json()["content"]["items"]
    by_evidence = {i["evidence_id"]: i["source_status"] for i in items}
    assert by_evidence[e1] == "OK"
    assert by_evidence[e2] == "MISSING"
    assert by_evidence[e3] == "CHANGED"
    # the stored snapshot itself still carries the historical names
    assert {i["evidence_id"]: i["display_name"] for i in items}[e2] == "将被删除"


def test_snapshot_missing_version_is_404(client, auth_headers, case_id):
    e1 = _mk_evidence(client, auth_headers, case_id, "A")
    pkg = _mk_package(client, auth_headers, case_id)
    _save(client, auth_headers, pkg["id"], 1, [{"evidence_id": e1}])
    _snapshot(client, auth_headers, pkg["id"], 2)
    resp = client.get(
        f"/api/v1/material-packages/{pkg['id']}/snapshots/99", headers=auth_headers
    )
    assert resp.status_code == 404
    assert _err_code(resp) == "SNAPSHOT_NOT_FOUND"


# ---------- 8. concurrency ----------


def test_stale_version_save_conflicts_and_preserves_state(client, auth_headers, case_id):
    e1 = _mk_evidence(client, auth_headers, case_id, "A")
    e2 = _mk_evidence(client, auth_headers, case_id, "B")
    pkg = _mk_package(client, auth_headers, case_id)
    ok = _save(client, auth_headers, pkg["id"], 1, [{"evidence_id": e1}])
    assert ok.status_code == 200

    # A second writer holding the old version must not silently win.
    stale = _save(
        client, auth_headers, pkg["id"], 1, [{"evidence_id": e2, "display_name": "覆盖尝试"}]
    )
    assert stale.status_code == 409
    assert _err_code(stale) == "VERSION_CONFLICT"

    detail = client.get(
        f"/api/v1/material-packages/{pkg['id']}", headers=auth_headers
    ).json()
    assert [(i["evidence_id"], i["display_name"]) for i in detail["items"]] == [(e1, "A")]


def test_stale_version_snapshot_conflicts(client, auth_headers, case_id):
    e1 = _mk_evidence(client, auth_headers, case_id, "A")
    pkg = _mk_package(client, auth_headers, case_id)
    _save(client, auth_headers, pkg["id"], 1, [{"evidence_id": e1}])
    resp = _snapshot(client, auth_headers, pkg["id"], 1)  # stale: now 2
    assert resp.status_code == 409
    assert _err_code(resp) == "VERSION_CONFLICT"


# ---------- 9. duplicate submits ----------


def test_duplicate_snapshot_submit_is_refused(client, auth_headers, case_id):
    e1 = _mk_evidence(client, auth_headers, case_id, "A")
    pkg = _mk_package(client, auth_headers, case_id)
    _save(client, auth_headers, pkg["id"], 1, [{"evidence_id": e1}])
    first = _snapshot(client, auth_headers, pkg["id"], 2)
    assert first.status_code == 201
    # Exact retry (double click): must not append a byte-identical version.
    again = _snapshot(client, auth_headers, pkg["id"], 2)
    assert again.status_code == 409
    assert _err_code(again) == "SNAPSHOT_DUPLICATE"
    history = client.get(
        f"/api/v1/material-packages/{pkg['id']}/snapshots", headers=auth_headers
    ).json()
    assert history["total"] == 1


def test_repeat_identical_save_is_stable(client, auth_headers, case_id):
    e1 = _mk_evidence(client, auth_headers, case_id, "A")
    pkg = _mk_package(client, auth_headers, case_id)
    payload = [{"evidence_id": e1}]
    first = _save(client, auth_headers, pkg["id"], 1, payload)
    assert first.status_code == 200
    version = first.json()["draft_version"]
    second = _save(client, auth_headers, pkg["id"], version, payload)
    assert second.status_code == 200
    items = second.json()["items"]
    assert len(items) == 1  # no duplicate row materialised
    assert items[0]["id"] == first.json()["items"][0]["id"]
    assert items[0]["item_order"] == 1


# ---------- 10. edges ----------


def test_snapshot_of_empty_package_is_409(client, auth_headers, case_id):
    pkg = _mk_package(client, auth_headers, case_id)
    resp = _snapshot(client, auth_headers, pkg["id"], 1)
    assert resp.status_code == 409
    assert _err_code(resp) == "EMPTY_PACKAGE"


def test_snapshot_of_archived_package_is_409(client, auth_headers, case_id):
    e1 = _mk_evidence(client, auth_headers, case_id, "A")
    pkg = _mk_package(client, auth_headers, case_id)
    _save(client, auth_headers, pkg["id"], 1, [{"evidence_id": e1}])
    assert client.patch(
        f"/api/v1/material-packages/{pkg['id']}",
        json={"status": "ARCHIVED"},
        headers=auth_headers,
    ).status_code == 200
    resp = _snapshot(client, auth_headers, pkg["id"], 2)
    assert resp.status_code == 409
    assert _err_code(resp) == "NOT_SNAPSHOTABLE"


def test_published_package_stays_editable(client, auth_headers, case_id):
    """Phase 9-C: publishing is user confirmation only — editing stays open."""
    e1 = _mk_evidence(client, auth_headers, case_id, "A")
    pkg = _mk_package(client, auth_headers, case_id)
    _save(client, auth_headers, pkg["id"], 1, [{"evidence_id": e1}])
    assert client.patch(
        f"/api/v1/material-packages/{pkg['id']}",
        json={"status": "PUBLISHED"},
        headers=auth_headers,
    ).status_code == 200
    # Still editable after publish.
    resp = _save(
        client, auth_headers, pkg["id"], 2,
        [{"evidence_id": e1, "display_name": "发布后修改"}],
    )
    assert resp.status_code == 200
    assert resp.json()["draft_version"] == 3
    # Publishing does not create a snapshot automatically.
    snaps = client.get(
        f"/api/v1/material-packages/{pkg['id']}/snapshots", headers=auth_headers
    ).json()
    assert snaps["total"] == 0
    # Snapshot creation stays available after publish.
    assert _snapshot(client, auth_headers, pkg["id"], 3).status_code == 201


def test_items_cannot_be_edited_after_archive(client, auth_headers, case_id):
    e1 = _mk_evidence(client, auth_headers, case_id, "A")
    pkg = _mk_package(client, auth_headers, case_id)
    _save(client, auth_headers, pkg["id"], 1, [{"evidence_id": e1}])
    assert client.patch(
        f"/api/v1/material-packages/{pkg['id']}",
        json={"status": "ARCHIVED"},
        headers=auth_headers,
    ).status_code == 200
    resp = _save(client, auth_headers, pkg["id"], 2, [])
    assert resp.status_code == 409
    assert _err_code(resp) == "NOT_EDITABLE"


def test_invalid_status_value_is_422(client, auth_headers, case_id):
    pkg = _mk_package(client, auth_headers, case_id)
    resp = client.patch(
        f"/api/v1/material-packages/{pkg['id']}",
        json={"status": "WHATEVER"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_delete_draft_without_snapshots(client, auth_headers, case_id):
    e1 = _mk_evidence(client, auth_headers, case_id, "A")
    pkg = _mk_package(client, auth_headers, case_id)
    _save(client, auth_headers, pkg["id"], 1, [{"evidence_id": e1}])
    resp = client.delete(
        f"/api/v1/material-packages/{pkg['id']}", headers=auth_headers
    )
    assert resp.status_code == 204
    assert (
        client.get(
            f"/api/v1/material-packages/{pkg['id']}", headers=auth_headers
        ).status_code
        == 404
    )


def test_delete_with_snapshots_is_refused(client, auth_headers, case_id):
    e1 = _mk_evidence(client, auth_headers, case_id, "A")
    pkg = _mk_package(client, auth_headers, case_id)
    _save(client, auth_headers, pkg["id"], 1, [{"evidence_id": e1}])
    _snapshot(client, auth_headers, pkg["id"], 2)
    resp = client.delete(
        f"/api/v1/material-packages/{pkg['id']}", headers=auth_headers
    )
    assert resp.status_code == 409
    assert _err_code(resp) == "HAS_SNAPSHOTS"
    # package still readable
    assert (
        client.get(
            f"/api/v1/material-packages/{pkg['id']}", headers=auth_headers
        ).status_code
        == 200
    )


def test_deleting_evidence_cascades_draft_items_but_not_snapshots(
    client, auth_headers, case_id
):
    """Rule 7: originals are never held hostage by the package."""
    e1 = _mk_evidence(client, auth_headers, case_id, "A")
    pkg = _mk_package(client, auth_headers, case_id)
    _save(client, auth_headers, pkg["id"], 1, [{"evidence_id": e1}])
    _snapshot(client, auth_headers, pkg["id"], 2)
    assert client.delete(f"/api/v1/evidence/{e1}", headers=auth_headers).status_code == 204

    detail = client.get(
        f"/api/v1/material-packages/{pkg['id']}", headers=auth_headers
    ).json()
    assert detail["item_count"] == 0  # draft row cascaded away

    snap = client.get(
        f"/api/v1/material-packages/{pkg['id']}/snapshots/1", headers=auth_headers
    ).json()
    assert snap["content"]["items"][0]["source_status"] == "MISSING"
    assert snap["content"]["items"][0]["evidence_id"] == e1  # history preserved


# ---------- 11. metadata parity (migration vs models) ----------


def test_metadata_tables_exist_in_test_database(db_session):
    """create_all built the test schema from the models: if the migration and
    the ORM drift apart, `alembic check` in the verification step reports it;
    here we only assert the three tables are registered on the metadata."""
    from app.db import Base

    from sqlalchemy import inspect as sa_inspect

    names = set(Base.metadata.tables)
    expected = {
        "material_packages",
        "material_package_items",
        "material_package_snapshots",
    }
    assert expected <= names
    # The test schema is built by create_all from the ORM metadata; the
    # migration parity itself is asserted by `alembic check` in the
    # verification step.
    live = set(sa_inspect(db_session.bind).get_table_names())
    assert expected <= live
