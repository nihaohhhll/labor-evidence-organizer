"""Phase 8-A3: evidence gap detection — rules, gates, API contract.

What is pinned here:
* empty case → 400 GAP_ANALYSIS_FAILED, no row (decision: keep the
  implemented 400, not the draft design's 409);
* SUCCESS rows are immutable per version, versions increment from 1;
* the two live rules (FACT_NO_EXPECTED_TYPE_SOURCE, EVENT_UNDATED_NO_ANCHOR)
  and the two skipped ones (EVENT_NO_EVIDENCE per decision 2,
  FACT_SINGLE_SOURCE per decision 4);
* expected/suggested types stay inside the EvidenceType vocabulary the
  classifier actually emits (docs/03 §4);
* the wording gates (neutrality → no-obligation → sources → schema) run
  over the final artefact inside the service, and a mutation test proves
  a violated gate fails the analysis instead of being silently stored;
* gap_id is deterministic across versions (cross-version fingerprint).
"""

from __future__ import annotations

import uuid

import pytest

from app.models.case_gap import CaseEvidenceGapResult
from app.models.event import Event
from app.services import evidence_gaps as gaps

# docs/03 §4 / app/ai/mock.py — the closed EvidenceType vocabulary.
VALID_EVIDENCE_TYPES = {
    "labor_contract",
    "company_notice",
    "chat_record",
    "bank_statement",
    "salary_statement",
    "attendance_record",
    "social_insurance",
    "identity_document",
    "company_registration",
    "work_record",
    "other",
}

OBLIGATION_EXAMPLES = [
    "必须提供合同",
    "应当说明情况",
    "需要补齐材料",
    "否则将无法受理",
    "这是法定义务",
    "适用举证责任规则",
]

NEUTRALITY_EXAMPLES = [
    "公司违法解除劳动关系",
    "公司存在违规行为",
    "本案必然胜诉",
    "可以主张赔偿金额",
]


def _make_evidence(
    db,
    case_id: str,
    number: int,
    title: str,
    category: str,
    summary: str | None = None,
    proof_purpose: str | None = None,
) -> object:
    from app.models.evidence import Evidence

    ev = Evidence(
        case_id=uuid.UUID(case_id),
        evidence_number=number,
        title=title,
        category=category,
        summary=summary,
        proof_purpose=proof_purpose,
        review_status="CONFIRMED",
    )
    db.add(ev)
    return ev


def _make_event(db, case_id: str, title: str, precision: str = "unknown") -> Event:
    ev = Event(case_id=uuid.UUID(case_id), title=title, precision=precision)
    db.add(ev)
    return ev


def _trigger(client, headers, case_id: str):
    return client.post(f"/api/v1/cases/{case_id}/evidence-gaps", headers=headers)


def _items(resp_json: dict) -> list[dict]:
    return (resp_json.get("gap_json") or {}).get("missing_items", [])


# --------------------------------------------------------------------------
# API contract
# --------------------------------------------------------------------------


def test_trigger_on_empty_case_fails_400_and_creates_nothing(client, auth_headers, case_id):
    resp = _trigger(client, auth_headers, case_id)
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "GAP_ANALYSIS_FAILED"

    assert client.get(
        f"/api/v1/cases/{case_id}/evidence-gaps", headers=auth_headers
    ).status_code == 404
    history = client.get(
        f"/api/v1/cases/{case_id}/evidence-gaps/history", headers=auth_headers
    ).json()
    assert history["total"] == 0 and history["results"] == []


def test_trigger_success_with_no_gaps(client, auth_headers, case_id, db_session):
    _make_evidence(
        db_session, case_id, 1, "劳动合同—a.txt", "labor_contract",
        summary="合同期限自2022年10月1日起至2025年9月30日止。",
        proof_purpose="用于证明双方存在劳动关系及约定期限这一事实。",
    )
    db_session.commit()

    resp = _trigger(client, auth_headers, case_id)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "SUCCESS"
    assert body["version"] == 1
    assert body["error_message"] is None
    assert body["gap_json"] == {"missing_items": []}


def test_versions_increment_and_stay_immutable(client, auth_headers, case_id, db_session):
    _make_evidence(db_session, case_id, 1, "聊天—a.txt", "chat_record",
                   summary="入职时间：2022-10-01")
    db_session.commit()

    first = _trigger(client, auth_headers, case_id)
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["version"] == 1

    second = _trigger(client, auth_headers, case_id)
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["version"] == 2
    assert second_body["id"] != first_body["id"]

    # the version-1 row was never rewritten
    frozen = db_session.get(CaseEvidenceGapResult, uuid.UUID(first_body["id"]))
    assert frozen is not None
    assert frozen.version == 1
    assert frozen.gap_json == first_body["gap_json"]

    latest = client.get(
        f"/api/v1/cases/{case_id}/evidence-gaps", headers=auth_headers
    ).json()
    assert latest["version"] == 2


def test_get_latest_404_before_first_run(client, auth_headers, case_id):
    resp = client.get(f"/api/v1/cases/{case_id}/evidence-gaps", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "GAP_NOT_FOUND"


def test_history_pagination(client, auth_headers, case_id, db_session):
    _make_evidence(db_session, case_id, 1, "考勤—a.txt", "attendance_record")
    db_session.commit()
    for _ in range(3):
        assert _trigger(client, auth_headers, case_id).status_code == 200

    page = client.get(
        f"/api/v1/cases/{case_id}/evidence-gaps/history?limit=2&offset=0",
        headers=auth_headers,
    ).json()
    assert page["total"] == 3
    assert [r["version"] for r in page["results"]] == [3, 2]

    rest = client.get(
        f"/api/v1/cases/{case_id}/evidence-gaps/history?limit=2&offset=2",
        headers=auth_headers,
    ).json()
    assert rest["total"] == 3
    assert [r["version"] for r in rest["results"]] == [1]


def test_all_endpoints_require_ownership(client, auth_headers, second_user_headers, case_id, db_session):
    _make_evidence(db_session, case_id, 1, "聊天—a.txt", "chat_record",
                   summary="入职时间：2022-10-01")
    db_session.commit()
    assert _trigger(client, auth_headers, case_id).status_code == 200

    for method, url in [
        ("post", f"/api/v1/cases/{case_id}/evidence-gaps"),
        ("get", f"/api/v1/cases/{case_id}/evidence-gaps"),
        ("get", f"/api/v1/cases/{case_id}/evidence-gaps/history"),
    ]:
        resp = getattr(client, method)(url, headers=second_user_headers)
        assert resp.status_code == 404, (method, url, resp.status_code, resp.text)


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------


def test_rule1_unsupported_fact_produces_traceable_gap(client, auth_headers, case_id, db_session):
    _make_evidence(db_session, case_id, 1, "聊天—a.txt", "chat_record",
                   summary="入职时间：2022-10-01")
    db_session.commit()

    resp = _trigger(client, auth_headers, case_id)
    assert resp.status_code == 200, resp.text
    items = _items(resp.json())
    assert [i["code"] for i in items] == ["FACT_NO_EXPECTED_TYPE_SOURCE"]

    gap = items[0]
    assert gap["priority"] == "medium"
    uuid.UUID(gap["gap_id"])
    assert len(gap["related_fact_ids"]) == 1
    uuid.UUID(gap["related_fact_ids"][0])
    assert set(gap["suggested_evidence_types"]) <= VALID_EVIDENCE_TYPES
    assert gap["sources"], "each gap must carry a source (wording gate 3)"
    assert gap["sources"][0]["kind"] == "evidence"
    assert "2022-10-01" in gap["sources"][0]["excerpt"]
    assert gap["check_basis"]["fact_label"] == "入职时间"
    assert gap["check_basis"]["checked_evidence_count"] == 1


def test_rule1_aggregates_multiple_sources_for_one_label(client, auth_headers, case_id, db_session):
    _make_evidence(db_session, case_id, 1, "聊天—a.txt", "chat_record",
                   summary="入职时间：2022-10-01")
    _make_evidence(db_session, case_id, 2, "聊天—b.txt", "chat_record",
                   summary="入职时间：2022-10-01")
    db_session.commit()

    resp = _trigger(client, auth_headers, case_id)
    assert resp.status_code == 200, resp.text
    items = _items(resp.json())
    assert len(items) == 1
    assert len(items[0]["sources"]) == 2


def test_rule1_suppressed_by_case_level_support(client, auth_headers, case_id, db_session):
    """A labor_contract anywhere in the case supports the 入职时间 label —
    even when the contract's own text never repeats the label."""
    _make_evidence(db_session, case_id, 1, "聊天—a.txt", "chat_record",
                   summary="入职时间：2022-10-01")
    _make_evidence(db_session, case_id, 2, "劳动合同—b.txt", "labor_contract",
                   summary="合同期限自2022年10月1日起至2025年9月30日止。")
    db_session.commit()

    resp = _trigger(client, auth_headers, case_id)
    assert resp.status_code == 200, resp.text
    assert _items(resp.json()) == []


def test_rule5_undated_event_without_evidence(client, auth_headers, case_id, db_session):
    _make_evidence(db_session, case_id, 1, "考勤—a.txt", "attendance_record")
    _make_event(db_session, case_id, "口头辞退", precision="unknown")
    db_session.commit()

    resp = _trigger(client, auth_headers, case_id)
    assert resp.status_code == 200, resp.text
    items = _items(resp.json())
    assert [i["code"] for i in items] == ["EVENT_UNDATED_NO_ANCHOR"]
    gap = items[0]
    assert gap["priority"] == "low"
    assert set(gap["suggested_evidence_types"]) <= VALID_EVIDENCE_TYPES
    assert "any" not in gap["suggested_evidence_types"]
    assert gap["sources"][0]["kind"] == "event"
    assert gap["sources"][0]["excerpt"] == "口头辞退"
    uuid.UUID(gap["gap_id"])


def test_rule5_suppressed_when_event_has_evidence_or_known_precision(
    client, auth_headers, case_id, db_session
):
    from app.models.evidence import EvidenceEvent

    ev = _make_evidence(db_session, case_id, 1, "考勤—a.txt", "attendance_record")
    anchored = _make_event(db_session, case_id, "已关联证据的事件", precision="unknown")
    _make_event(db_session, case_id, "有精确日期的事件", precision="day")
    db_session.flush()
    db_session.add(EvidenceEvent(evidence_id=ev.id, event_id=anchored.id))
    db_session.commit()

    resp = _trigger(client, auth_headers, case_id)
    assert resp.status_code == 200, resp.text
    assert _items(resp.json()) == []


def test_skipped_rules_never_appear_in_output(client, auth_headers, case_id, db_session):
    """Decision 2: EVENT_NO_EVIDENCE skipped; decision 4: FACT_SINGLE_SOURCE
    skipped. A case that would otherwise trigger them emits nothing for them."""
    _make_evidence(db_session, case_id, 1, "聊天—a.txt", "chat_record",
                   summary="入职时间：2022-10-01")  # single source for the label
    _make_event(db_session, case_id, "有精确日期的事件", precision="day")  # no evidence, but dated
    db_session.commit()

    resp = _trigger(client, auth_headers, case_id)
    assert resp.status_code == 200, resp.text
    codes = {i["code"] for i in _items(resp.json())}
    assert "FACT_SINGLE_SOURCE" not in codes
    assert "EVENT_NO_EVIDENCE" not in codes


def test_gap_id_stable_across_versions(client, auth_headers, case_id, db_session):
    _make_evidence(db_session, case_id, 1, "聊天—a.txt", "chat_record",
                   summary="入职时间：2022-10-01")
    db_session.commit()

    first = _trigger(client, auth_headers, case_id).json()
    second = _trigger(client, auth_headers, case_id).json()
    assert first["version"] == 1 and second["version"] == 2

    first_ids = sorted(i["gap_id"] for i in _items(first))
    second_ids = sorted(i["gap_id"] for i in _items(second))
    assert first_ids and first_ids == second_ids


# --------------------------------------------------------------------------
# Wording gates
# --------------------------------------------------------------------------


def test_generated_wording_passes_both_gates(client, auth_headers, case_id, db_session):
    _make_evidence(db_session, case_id, 1, "聊天—a.txt", "chat_record",
                   summary="入职时间：2022-10-01；薪资：7500元")
    _make_event(db_session, case_id, "口头辞退", precision="unknown")
    db_session.commit()

    resp = _trigger(client, auth_headers, case_id)
    assert resp.status_code == 200, resp.text
    items = _items(resp.json())
    assert len(items) >= 2
    for item in items:
        for text in (item["title"], item["description"]):
            for word in gaps.OBLIGATION_WORDS:
                assert word not in text, (word, text)
            for word in gaps.NEUTRALITY_FORBIDDEN:
                assert word not in text, (word, text)


def test_gate_catches_obligation_word_in_generated_title(
    client, auth_headers, case_id, db_session, monkeypatch
):
    """Mutation: force a rule to emit an obligation word in its title; the
    service-layer gate must fail the analysis instead of storing it."""
    _make_evidence(db_session, case_id, 1, "聊天—a.txt", "chat_record",
                   summary="没有触发词的普通材料")
    db_session.commit()

    evil_label = "必须补齐的材料"
    monkeypatch.setitem(gaps.EXPECTED_BY_LABEL, evil_label, ["labor_contract"])

    def evil_extractor(case_id_, evidence_list):
        return [
            gaps.Fact(
                id=uuid.uuid5(gaps._FACT_NS, f"{case_id_}:{evil_label}"),
                label=evil_label,
                value=None,
                evidence_ids=[evidence_list[0].id],
            )
        ]

    monkeypatch.setattr(gaps, "_extract_facts_from_evidence", evil_extractor)

    resp = _trigger(client, auth_headers, case_id)
    assert resp.status_code == 400, resp.text
    assert "暗示义务" in resp.text, resp.text
    # nothing was persisted
    assert client.get(
        f"/api/v1/cases/{case_id}/evidence-gaps", headers=auth_headers
    ).status_code == 404


def test_gate_catches_neutrality_word_in_generated_title(
    client, auth_headers, case_id, db_session, monkeypatch
):
    _make_evidence(db_session, case_id, 1, "聊天—a.txt", "chat_record",
                   summary="没有触发词的普通材料")
    db_session.commit()

    evil_label = "公司违法解除的情况"
    monkeypatch.setitem(gaps.EXPECTED_BY_LABEL, evil_label, ["labor_contract"])

    def evil_extractor(case_id_, evidence_list):
        return [
            gaps.Fact(
                id=uuid.uuid5(gaps._FACT_NS, f"{case_id_}:{evil_label}"),
                label=evil_label,
                value=None,
                evidence_ids=[evidence_list[0].id],
            )
        ]

    monkeypatch.setattr(gaps, "_extract_facts_from_evidence", evil_extractor)

    resp = _trigger(client, auth_headers, case_id)
    assert resp.status_code == 400, resp.text
    assert "非中性" in resp.text, resp.text


@pytest.mark.parametrize("text", OBLIGATION_EXAMPLES)
def test_assert_no_obligation_rejects_each_family(text: str):
    with pytest.raises(ValueError, match="暗示义务"):
        gaps.assert_no_obligation(text)


@pytest.mark.parametrize("text", NEUTRALITY_EXAMPLES)
def test_assert_neutral_rejects_conclusion_words(text: str):
    with pytest.raises(ValueError, match="非中性"):
        gaps.assert_neutral(text)


def test_gates_allow_clean_text():
    gaps.assert_no_obligation("案件材料中已提及入职时间，但未发现预期类型的证据支持。")
    gaps.assert_neutral("案件材料中已提及入职时间，但未发现预期类型的证据支持。")
    gaps.assert_no_obligation("")
    gaps.assert_neutral(None)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Service units
# --------------------------------------------------------------------------


def test_extract_facts_patterns_and_aggregation(db_session, case_id):
    from sqlalchemy import select

    from app.models.evidence import Evidence

    case_uuid = uuid.UUID(case_id)
    _make_evidence(db_session, case_id, 1, "聊天—a.txt", "chat_record",
                   summary="入职时间：2022-10-01，薪资：7500元")
    _make_evidence(db_session, case_id, 2, "合同—b.txt", "labor_contract",
                   summary="合同开始时间：2022-10-01", proof_purpose="岗位：软件工程师。")
    _make_evidence(db_session, case_id, 3, "流水—c.txt", "bank_statement",
                   summary="没有触发词的普通材料")
    db_session.commit()

    evidence_list = list(db_session.scalars(select(Evidence).where(Evidence.case_id == case_uuid)).all())
    facts = gaps._extract_facts_from_evidence(case_uuid, evidence_list)
    labels = {f.label for f in facts}
    assert labels == {"入职时间", "薪资", "合同开始时间", "岗位"}
    # labels are deterministic uuid5(case, label) values
    for f in facts:
        assert f.id == uuid.uuid5(gaps._FACT_NS, f"{case_id}:{f.label}")
    by_label = {f.label: f for f in facts}
    assert len(by_label["入职时间"].evidence_ids) == 1
    assert by_label["薪资"].value == "7500元"


def test_next_gap_version_starts_at_one(db_session, case_id):
    case_uuid = uuid.UUID(case_id)
    assert gaps._next_gap_version(db_session, case_uuid) == 1
    db_session.add(
        CaseEvidenceGapResult(
            case_id=case_uuid, version=1, status="SUCCESS", gap_json={"missing_items": []}
        )
    )
    db_session.commit()
    assert gaps._next_gap_version(db_session, case_uuid) == 2


# --------------------------------------------------------------------------
# Integration with the real (mock) pipeline
# --------------------------------------------------------------------------


def test_full_mock_pipeline_produces_valid_result(client, auth_headers, case_id):
    from tests.helpers import SAMPLE_TEXT, make_txt, upload

    resp = upload(client, auth_headers, case_id, "contract.txt", make_txt(SAMPLE_TEXT))
    assert resp.status_code == 201, resp.text
    file_id = resp.json()["files"][0]["id"]
    assert client.post(f"/api/v1/files/{file_id}/analyze", headers=auth_headers).status_code == 200

    evidence = client.get(f"/api/v1/cases/{case_id}/evidence", headers=auth_headers).json()["evidence"]
    assert evidence, "pipeline should have suggested evidence"
    for row in evidence:
        assert client.post(
            f"/api/v1/evidence/{row['id']}/confirm", headers=auth_headers
        ).status_code == 200

    resp = _trigger(client, auth_headers, case_id)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "SUCCESS"
    # Mock summaries never repeat the fact labels verbatim, so no Rule-1 gap
    # fires; this pins the current pipeline's end-to-end behaviour.
    for item in _items(body):
        assert item["code"] in {"FACT_NO_EXPECTED_TYPE_SOURCE", "EVENT_UNDATED_NO_ANCHOR"}
        assert set(item["suggested_evidence_types"]) <= VALID_EVIDENCE_TYPES
