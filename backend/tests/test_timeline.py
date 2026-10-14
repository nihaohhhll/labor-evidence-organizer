"""Phase 6: timeline construction, editing and merging."""

from __future__ import annotations

import uuid

from tests.helpers import make_txt, upload


def _confirmed_evidence(client, headers, case_id, count=1):
    """Upload + analyze + confirm `count` evidence rows."""
    ids = []
    for i in range(count):
        data = make_txt(
            f"劳动合同 甲方：某某科技有限公司 入职日期：202{2}年10月{i + 1}日 月工资7500元"
        )
        fid = upload(client, headers, case_id, f"doc{i}.txt", data).json()["files"][0]["id"]
        client.post(f"/api/v1/files/{fid}/analyze", headers=headers)
    rows = client.get(f"/api/v1/cases/{case_id}/evidence", headers=headers).json()["evidence"]
    for row in rows:
        client.post(f"/api/v1/evidence/{row['id']}/confirm", headers=headers)
    return [r["id"] for r in rows]


def test_build_timeline_from_confirmed_evidence(client, auth_headers, case_id):
    """US-005: events are derived from confirmed, dated evidence."""
    _confirmed_evidence(client, auth_headers, case_id, count=2)

    resp = client.post(f"/api/v1/cases/{case_id}/events/build", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    events = resp.json()["events"]
    assert len(events) == 2
    assert all(e["event_date"] is not None for e in events)
    assert all(e["precision"] == "day" for e in events)


def test_build_timeline_is_idempotent(client, auth_headers, case_id):
    """Calling build twice must not duplicate events."""
    _confirmed_evidence(client, auth_headers, case_id, count=2)
    first = client.post(f"/api/v1/cases/{case_id}/events/build", headers=auth_headers).json()
    second = client.post(f"/api/v1/cases/{case_id}/events/build", headers=auth_headers).json()
    assert len(first["events"]) == len(second["events"]) == 2


def test_unconfirmed_evidence_is_excluded(client, auth_headers, case_id):
    """Only human-confirmed evidence should shape the timeline."""
    data = make_txt("劳动合同 入职日期：2022年10月1日 月工资7500元")
    fid = upload(client, auth_headers, case_id, "a.txt", data).json()["files"][0]["id"]
    client.post(f"/api/v1/files/{fid}/analyze", headers=auth_headers)

    events = client.post(f"/api/v1/cases/{case_id}/events/build", headers=auth_headers).json()
    assert events["events"] == []


def test_events_are_sorted_by_date(client, auth_headers, case_id):
    _confirmed_evidence(client, auth_headers, case_id, count=3)
    events = client.post(f"/api/v1/cases/{case_id}/events/build", headers=auth_headers).json()["events"]
    dates = [e["event_date"] for e in events]
    assert dates == sorted(dates)


def test_create_manual_event_is_confirmed(client, auth_headers, case_id):
    resp = client.post(
        f"/api/v1/cases/{case_id}/events",
        json={"title": "hr口头通知辞退", "event_date": "2024-03-15", "precision": "day"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["review_status"] == "CONFIRMED"
    assert body["event_date"] == "2024-03-15"


def test_update_event(client, auth_headers, case_id):
    eid = client.post(
        f"/api/v1/cases/{case_id}/events",
        json={"title": "原始标题", "event_date": "2024-03-15"},
        headers=auth_headers,
    ).json()["id"]

    resp = client.patch(
        f"/api/v1/events/{eid}",
        json={"title": "修正后的标题", "precision": "unknown", "event_date": None},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "修正后的标题"
    assert resp.json()["precision"] == "unknown"


def test_invalid_precision_rejected(client, auth_headers, case_id):
    resp = client.post(
        f"/api/v1/cases/{case_id}/events",
        json={"title": "x", "precision": "exact"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_merge_collapses_events_and_keeps_evidence_links(client, auth_headers, case_id):
    """US: 合并 — survivor keeps every evidence link."""
    _confirmed_evidence(client, auth_headers, case_id, count=2)
    client.post(f"/api/v1/cases/{case_id}/events/build", headers=auth_headers)
    events = client.get(f"/api/v1/cases/{case_id}/events", headers=auth_headers).json()["events"]
    assert len(events) == 2

    ids = [e["id"] for e in events]
    merged = client.post(
        "/api/v1/events/merge",
        json={"event_ids": ids, "title": "合并后的事件"},
        headers=auth_headers,
    )
    assert merged.status_code == 200, merged.text
    assert merged.json()["title"] == "合并后的事件"

    # Only the survivor remains in the listing.
    after = client.get(f"/api/v1/cases/{case_id}/events", headers=auth_headers).json()["events"]
    assert len(after) == 1
    assert after[0]["id"] == merged.json()["id"]


def test_merge_rejects_single_event(client, auth_headers, case_id):
    eid = client.post(
        f"/api/v1/cases/{case_id}/events", json={"title": "a"}, headers=auth_headers
    ).json()["id"]
    resp = client.post("/api/v1/events/merge", json={"event_ids": [eid]}, headers=auth_headers)
    assert resp.status_code == 422  # pydantic min_length=2


def test_merge_is_committed_to_database(client, auth_headers, case_id):
    """The merge route must commit; the shared test session would otherwise
    mask a missing commit because it never rolls back between requests."""
    _confirmed_evidence(client, auth_headers, case_id, count=2)
    client.post(f"/api/v1/cases/{case_id}/events/build", headers=auth_headers)
    events = client.get(f"/api/v1/cases/{case_id}/events", headers=auth_headers).json()["events"]
    ids = [e["id"] for e in events]
    merged = client.post("/api/v1/events/merge", json={"event_ids": ids}, headers=auth_headers)
    assert merged.status_code == 200, merged.text

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    from app.config import get_settings
    from app.models.event import Event

    engine = create_engine(get_settings().test_database_url, pool_pre_ping=True, future=True)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    try:
        live = list(
            db.scalars(select(Event).where(Event.case_id == uuid.UUID(case_id)).where(Event.merged_into_id.is_(None))).all()
        )
        assert len(live) == 1, f"merge not committed: {len(live)} live events remain"
        assert str(live[0].id) == merged.json()["id"]
    finally:
        db.close()
        engine.dispose()


def test_delete_event(client, auth_headers, case_id):
    eid = client.post(
        f"/api/v1/cases/{case_id}/events", json={"title": "to delete"}, headers=auth_headers
    ).json()["id"]
    assert client.delete(f"/api/v1/events/{eid}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/v1/events/{eid}", headers=auth_headers).status_code == 404


def test_timeline_requires_ownership(client, auth_headers, second_user_headers, case_id):
    _confirmed_evidence(client, auth_headers, case_id, count=1)
    eid = client.post(
        f"/api/v1/cases/{case_id}/events", json={"title": "mine"}, headers=auth_headers
    ).json()["id"]

    assert (
        client.get(f"/api/v1/cases/{case_id}/events", headers=second_user_headers).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/cases/{case_id}/events/build", headers=second_user_headers
        ).status_code
        == 404
    )
    assert client.get(f"/api/v1/events/{eid}", headers=second_user_headers).status_code == 404
    assert (
        client.patch(
            f"/api/v1/events/{eid}", json={"title": "hacked"}, headers=second_user_headers
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/v1/events/{eid}", headers=second_user_headers).status_code == 404
    )


def test_event_without_date_is_reported_not_invented(client, auth_headers, case_id):
    """docs/07: "not found" must not be silently upgraded to a guess."""
    resp = client.post(
        f"/api/v1/cases/{case_id}/events",
        json={"title": "时间未知的沟通", "precision": "unknown"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["event_date"] is None
    assert resp.json()["precision"] == "unknown"
