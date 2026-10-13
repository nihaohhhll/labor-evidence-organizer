"""Timeline service: derive events from evidence and merge duplicates.

Rules (docs/08_PROMPT_SPEC timeline section):
* only events the materials actually support are created;
* several evidence rows describing the same event suggest a merge instead of
  silently duplicating the event.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evidence import Evidence, EvidenceEvent
from app.models.event import Event


def _dedupe_key(ev: Evidence) -> tuple:
    """Group evidence by (date, normalised title) so repeats collapse."""
    title = (ev.title or "").strip().lower()
    return (ev.event_date, title)


def _find_existing_event(
    db: Session, case_id: uuid.UUID, event_date: date | None, title: str
) -> Event | None:
    """Return a live event already representing (date, title), if any.

    Without this, every call to `build_timeline` would append a fresh copy of
    the same event — the operation would not be idempotent.
    """
    rows = db.scalars(
        select(Event).where(
            Event.case_id == case_id,
            Event.merged_into_id.is_(None),
            Event.title == title[:300],
        )
    ).all()
    for row in rows:
        if row.event_date == event_date:
            return row
    return None


def build_timeline(db: Session, case_id: uuid.UUID, *, only_confirmed: bool = True) -> list[Event]:
    """Create timeline events from evidence that has a date.

    Already-existing events are reused, so calling this twice is idempotent.
    """
    stmt = select(Evidence).where(Evidence.case_id == case_id)
    if only_confirmed:
        stmt = stmt.where(Evidence.review_status == "CONFIRMED")

    evidence_rows = list(db.scalars(stmt.order_by(Evidence.event_date.asc().nulls_last())).all())

    # Group evidence that describes the same dated event.
    groups: dict[tuple, list[Evidence]] = {}
    for ev in evidence_rows:
        if ev.event_date is None:
            continue
        groups.setdefault(_dedupe_key(ev), []).append(ev)

    created: list[Event] = []
    for (event_date, _title), members in sorted(
        groups.items(), key=lambda kv: (kv[0][0] or date.min, kv[0][1])
    ):
        first = members[0]
        title = first.title[:300]

        # Reuse a matching event instead of creating a duplicate.
        event = _find_existing_event(db, case_id, event_date, title)
        if event is None:
            event = Event(
                case_id=case_id,
                event_date=event_date,
                precision="day",
                title=title,
                description=first.summary,
                confidence=None,
                review_status="PENDING",
            )
            db.add(event)
            db.flush()

        # Confidences are tracked on evidence, not on the event, so a rebuild
        # cannot silently rewrite a human-edited description.
        for member in members:
            already = db.scalar(
                select(EvidenceEvent).where(
                    EvidenceEvent.evidence_id == member.id,
                    EvidenceEvent.event_id == event.id,
                )
            )
            if already is None:
                db.add(EvidenceEvent(evidence_id=member.id, event_id=event.id))
        created.append(event)

    return created


def merge_events(
    db: Session, user_id: uuid.UUID, event_ids: list[uuid.UUID], title: str | None = None
) -> Event:
    """Merge several events into the earliest one, keeping evidence links."""
    if len(event_ids) < 2:
        raise ValueError("至少需要两个事件才能合并。")

    rows = list(db.scalars(select(Event).where(Event.id.in_(event_ids))).all())
    if len(rows) != len(set(event_ids)):
        raise ValueError("部分事件不存在。")

    case_ids = {r.case_id for r in rows}
    if len(case_ids) != 1:
        raise ValueError("只能合并同一案件内的事件。")

    # Confirm ownership of the whole group at once.
    from app.services.files import get_owned_case

    get_owned_case(db, rows[0].case_id, user_id)

    rows.sort(key=lambda r: (r.event_date is None, r.event_date or date.min))
    survivor, *rest = rows

    if title:
        survivor.title = title[:300]
    survivor.review_status = "CONFIRMED"

    for other in rest:
        for link in db.scalars(
            select(EvidenceEvent).where(EvidenceEvent.event_id == other.id)
        ).all():
            exists = db.scalar(
                select(EvidenceEvent).where(
                    EvidenceEvent.evidence_id == link.evidence_id,
                    EvidenceEvent.event_id == survivor.id,
                )
            )
            if exists is None:
                db.add(EvidenceEvent(evidence_id=link.evidence_id, event_id=survivor.id))
            db.delete(link)
        other.merged_into_id = survivor.id

    db.flush()
    return survivor


def timeline_alerts(events: list[Event]) -> list[dict]:
    """Surface timeline quality issues for the UI (A2 lesson: use structured
    fields, never display text, to decide a state — engineering log §3.6)."""
    alerts: list[dict] = []
    for ev in events:
        # `precision` is the structured truth; the title may read "时间未知".
        if ev.event_date is None or ev.precision == "unknown":
            alerts.append(
                {
                    "event_id": str(ev.id),
                    "level": "WARN",
                    "code": "EVENT_NO_DATE",
                    "message": f"事件「{ev.title}」缺少确切日期。",
                }
            )
        if len(ev.evidence) == 1:
            alerts.append(
                {
                    "event_id": str(ev.id),
                    "level": "INFO",
                    "code": "EVENT_SINGLE_SOURCE",
                    "message": f"事件「{ev.title}」目前只有一份证据支持。",
                }
            )
    return alerts
