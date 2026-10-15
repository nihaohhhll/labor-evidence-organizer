"""Evidence gaps detection service (Phase 8-A3).

Deterministic rules only — no AI. Every rule describes *what was found in
the case materials*, never what exists in the real world or what anyone is
obliged to provide (docs/03 §A3, engineering log §6).

Gates run in the service over the final artefact, in the order fixed by the
design: neutrality → no-obligation wording → source traceability → schema.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.case_gap import CaseEvidenceGapResult
from app.models.evidence import Evidence
from app.models.event import Event
from app.schemas import GapJson

logger = logging.getLogger(__name__)

# Expected evidence types by fact label. Values must stay inside the
# EvidenceType vocabulary the classifier actually produces (docs/03 §4 and
# app/ai/mock.py): salary_statement/bank_statement — NOT the engineering
# log's outdated salary_record/bank_record.
EXPECTED_BY_LABEL: dict[str, list[str]] = {
    "入职时间": ["labor_contract", "work_record", "attendance_record"],
    "合同开始时间": ["labor_contract"],
    "离职时间": ["labor_contract", "company_notice", "chat_record"],
    "薪资": ["labor_contract", "salary_statement", "bank_statement"],
    "岗位": ["labor_contract", "work_record"],
    "用人单位": ["labor_contract", "company_registration"],
}

# Evidence types that can anchor an undated event (Rule 5). Kept inside the
# closed EvidenceType vocabulary; "any" from the draft design is not a type.
TIME_ANCHOR_TYPES = ["chat_record", "attendance_record", "work_record"]

OBLIGATION_WORDS = [
    "必须",
    "应当",
    "应",
    "需",
    "需要",
    "务必",
    "须",
    "否则",
    "不然",
    "否则后果",
    "法定义务",
    "举证责任",
    "有义务",
    "应提供",
    "必须提供",
]

NEUTRALITY_FORBIDDEN = [
    "违法",
    "违规",
    "犯罪",
    "赔偿",
    "胜诉",
    "败诉",
    "必然",
    "一定会",
    "绝对",
    "完全正确",
    "100%",
]


def assert_no_obligation(text: str) -> None:
    """Ensure text does not imply obligation (A3 decision 5: separate list)."""
    if not text:
        return
    for w in OBLIGATION_WORDS:
        if w in text:
            raise ValueError(f"措辞中含有可能暗示义务的表述：{w}")


def assert_neutral(text: str) -> None:
    """Ensure text draws no legal conclusion (gate 1 of the A3 wording gates)."""
    if not text:
        return
    for f in NEUTRALITY_FORBIDDEN:
        if f in text:
            raise ValueError(f"措辞中含有非中性表述：{f}")


# Deterministic namespaces: identical inputs always yield identical ids, so
# gap_id works as the cross-version fingerprint the design asks for.
_FACT_NS = uuid.uuid5(uuid.NAMESPACE_URL, "labor-evidence-organizer/a3/fact")
_GAP_NS = uuid.uuid5(uuid.NAMESPACE_URL, "labor-evidence-organizer/a3/gap")


@dataclass
class Fact:
    """A fact label mentioned in the case materials (no fact table exists).

    id = uuid5(case_id, label): deterministic, stable across runs."""

    id: uuid.UUID
    label: str
    value: str | None
    evidence_ids: list[uuid.UUID]


_FACT_PATTERNS: list[tuple[str, str]] = [
    # Prefix form: "入职时间：2022-03-01"
    (r"入职时间[：:为是]\s*(\d{4}[-年/]\d{1,2}[-月/]\d{1,2})", "入职时间"),
    (r"合同开始时间[：:为是]\s*(\d{4}[-年/]\d{1,2}[-月/]\d{1,2})", "合同开始时间"),
    (r"离职时间[：:为是]\s*(\d{4}[-年/]\d{1,2}[-月/]\d{1,2})", "离职时间"),
    (r"薪资[：:为是]\s*([0-9,]+元)", "薪资"),
    (r"工资[：:为是]\s*([0-9,]+元)", "薪资"),
    (r"岗位[：:为是]\s*(.+?)(?:[,，。；]|$)", "岗位"),
    (r"用人单位[：:为是]\s*(.+?)(?:[,，。；]|$)", "用人单位"),
    # Narrative form (AI summaries): "于2022年3月1日入职" / "月工资10000元"
    (r"(?:于|自|从)?(\d{4}[-年/]\d{1,2}[-月/]\d{1,2})[日号]?(?:起)?(?:入职|入职时间|开始工作)", "入职时间"),
    (r"(?:合同期限|合同|期限)(?:自|从|：)?(\d{4}[-年/]\d{1,2}[-月/]\d{1,2})", "合同开始时间"),
    (r"(?:月工资|月薪|工资标准|工资构?成|合计)[^\d]{0,6}([0-9,]+(?:\.\d+)?)\s*元", "薪资"),
    (r"(?:基本工资)[^\d]{0,4}([0-9,]+)\s*元", "薪资"),
    (r"(?:担任|岗位为|工作岗位)[：:]?\s*([^\s,，。；、]{2,10})", "岗位"),
    (r"(?:用人单位|甲方|公司全称|单位名称)[：:为是]\s*([\u4e00-\u9fff]{2,30}(?:有限公司|公司|集团|厂|院|中心|事务所))", "用人单位"),
]


def _extract_facts_from_evidence(
    case_id: uuid.UUID, evidence_list: list[Evidence]
) -> list[Fact]:
    """Collect fact labels mentioned anywhere in the case materials.

    One Fact per (case, label); every mentioning evidence is remembered as a
    source. Only labels the rules know how to check are kept.
    """
    found: dict[str, Fact] = {}
    for ev in evidence_list:
        text = " ".join(
            filter(None, [ev.title, ev.summary or "", ev.proof_purpose or ""])
        )
        for pat, label in _FACT_PATTERNS:
            if label not in EXPECTED_BY_LABEL:
                continue
            m = re.search(pat, text)
            if not m:
                continue
            fact = found.get(label)
            if fact is None:
                fact = Fact(
                    id=uuid.uuid5(_FACT_NS, f"{case_id}:{label}"),
                    label=label,
                    value=m.group(1).strip(),
                    evidence_ids=[],
                )
                found[label] = fact
            if ev.id not in fact.evidence_ids:
                fact.evidence_ids.append(ev.id)
    return list(found.values())


def _excerpt_of(ev: Evidence) -> str | None:
    return ev.summary or ev.proof_purpose or ev.title or None


def _next_gap_version(db: Session, case_id: uuid.UUID) -> int:
    current = db.scalar(
        select(func.max(CaseEvidenceGapResult.version))
        .where(CaseEvidenceGapResult.case_id == case_id)
    )
    return int(current or 0) + 1


def _run_gates(missing_items: list[dict]) -> None:
    """Design gate order (engineering log §6.4): neutrality → no-obligation
    → source traceability → schema, all over the final artefact.

    Only the system's own prose (title/description) is wording-gated;
    `sources[].excerpt` is a quote from the user's materials and must stay
    verbatim — labour-dispute evidence routinely contains words like
    "违法", and gating quotes would fail the whole analysis on user content.
    """
    for item in missing_items:
        for text in (item["title"], item["description"]):
            assert_neutral(text)
            assert_no_obligation(text)
        if not item.get("sources"):
            raise ValueError("缺口条目缺少来源材料，无法追溯。")
    GapJson(missing_items=missing_items)


def analyze_evidence_gaps(
    db: Session, case_id: uuid.UUID, user_id: uuid.UUID | None = None
) -> CaseEvidenceGapResult:
    """Analyze evidence gaps for a case (A3)."""
    evidence_list = list(
        db.scalars(select(Evidence).where(Evidence.case_id == case_id)).all()
    )
    events = list(db.scalars(select(Event).where(Event.case_id == case_id)).all())

    if not evidence_list and not events:
        raise ValueError("案件中没有材料或事件，无法生成证据缺口分析")

    facts = _extract_facts_from_evidence(case_id, evidence_list)
    missing_items: list[dict] = []
    evidence_by_id = {ev.id: ev for ev in evidence_list}

    # Rule FACT_NO_EXPECTED_TYPE_SOURCE: the label is mentioned in the
    # materials, but the case holds no evidence of an expected type.
    # Support is checked case-wide: one labor_contract anywhere counts.
    for fact in facts:
        expected = EXPECTED_BY_LABEL.get(fact.label, [])
        if not expected:
            continue
        if any(ev.category in expected for ev in evidence_list):
            continue
        sources = [
            {
                "kind": "evidence",
                "id": str(src_id),
                "excerpt": _excerpt_of(evidence_by_id[src_id]),
            }
            for src_id in fact.evidence_ids
            if src_id in evidence_by_id
        ]
        missing_items.append(
            {
                "code": "FACT_NO_EXPECTED_TYPE_SOURCE",
                "title": f"缺少{fact.label}相关证据",
                "description": f"案件材料中已提及{fact.label}，但未发现预期类型的证据支持。",
                "related_fact_ids": [str(fact.id)],
                "suggested_evidence_types": list(expected),
                "priority": "medium",
                "gap_id": str(uuid.uuid5(_GAP_NS, f"FACT_NO_EXPECTED_TYPE_SOURCE:{case_id}:{fact.id}")),
                "sources": sources,
                "check_basis": {
                    "fact_label": fact.label,
                    "fact_value": fact.value,
                    "expected_types": expected,
                    "checked_evidence_count": len(evidence_list),
                },
            }
        )

    # Rule EVENT_UNDATED_NO_ANCHOR: a confirmed-timing-unknown event with no
    # linked evidence that could pin its time. EVENT_NO_EVIDENCE is skipped
    # (A3 decision 2) to avoid duplicating A2's panel; FACT_SINGLE_SOURCE is
    # reported nowhere (A3 decision 4: not a gap).
    for ev in events:
        if ev.precision == "unknown" and not ev.evidence:
            missing_items.append(
                {
                    "code": "EVENT_UNDATED_NO_ANCHOR",
                    "title": "无日期事件缺少时间锚点",
                    "description": "案件中存在无精确日期的事件，建议补充能确定时间的证据材料。",
                    "related_fact_ids": [],
                    "suggested_evidence_types": list(TIME_ANCHOR_TYPES),
                    "priority": "low",
                    "gap_id": str(uuid.uuid5(_GAP_NS, f"EVENT_UNDATED_NO_ANCHOR:{case_id}:{ev.id}")),
                    "sources": [
                        {
                            "kind": "event",
                            "id": str(ev.id),
                            "excerpt": ev.description or ev.title,
                        }
                    ],
                    "check_basis": {
                        "event_id": str(ev.id),
                        "precision": ev.precision,
                        "checked_event_count": len(events),
                    },
                }
            )

    _run_gates(missing_items)

    version = _next_gap_version(db, case_id)
    result = CaseEvidenceGapResult(
        case_id=case_id,
        version=version,
        status="SUCCESS",
        gap_json={"missing_items": missing_items},
        created_by=user_id,
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return result
