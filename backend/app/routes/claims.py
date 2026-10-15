"""Claim routes — 仲裁请求 CRUD + evidence/event links (workbench phase)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, select

from app.deps import CurrentUser, DbDep, owned_case_or_404
from app.models.claim import Claim, ClaimEvent, ClaimStatus
from app.models.event import Event
from app.models.evidence import Evidence
from app.schemas import ClaimCreate, ClaimDetailOut, ClaimListOut, ClaimUpdate
from app.services.audit import AuditAction, record as audit

router = APIRouter()


def _get_owned_claim(db, user, claim_id: uuid.UUID) -> Claim:
    row = db.scalar(select(Claim).where(Claim.id == claim_id))
    if row is None:
        raise HTTPException(
            404, detail={"code": "CLAIM_NOT_FOUND", "message": "Claim not found."}
        )
    owned_case_or_404(db, row.case_id, user.id)
    return row


def _validate_links(db, case_id: uuid.UUID, evidence_ids, event_ids) -> None:
    """Every linked entity must exist and belong to the same case."""
    if evidence_ids:
        rows = list(db.scalars(select(Evidence).where(Evidence.id.in_(evidence_ids))).all())
        found = {r.id for r in rows}
        if len(found) != len(set(evidence_ids)):
            raise HTTPException(
                404, detail={"code": "EVIDENCE_NOT_FOUND", "message": "Evidence not found."}
            )
        if any(r.case_id != case_id for r in rows):
            raise HTTPException(
                404, detail={"code": "EVIDENCE_NOT_FOUND", "message": "Evidence not in this case."}
            )
    if event_ids:
        rows = list(db.scalars(select(Event).where(Event.id.in_(event_ids))).all())
        found = {r.id for r in rows}
        if len(found) != len(set(event_ids)):
            raise HTTPException(
                404, detail={"code": "EVENT_NOT_FOUND", "message": "Event not found."}
            )
        if any(r.case_id != case_id for r in rows):
            raise HTTPException(
                404, detail={"code": "EVENT_NOT_FOUND", "message": "Event not in this case."}
            )


def _set_event_links(db, claim: Claim, event_ids: list[uuid.UUID]) -> None:
    db.execute(delete(ClaimEvent).where(ClaimEvent.claim_id == claim.id))
    for eid in dict.fromkeys(event_ids):
        db.add(ClaimEvent(claim_id=claim.id, event_id=eid))


def _set_evidence_links(db, claim: Claim, evidence_ids: list[uuid.UUID]) -> None:
    # The evidence_claims join is owned by the Evidence side (EvidenceClaim);
    # go through the ORM collection so backrefs stay consistent.
    claim.evidence = list(
        db.scalars(select(Evidence).where(Evidence.id.in_(evidence_ids))).all()
    ) if evidence_ids else []


def _detail_out(db, claim: Claim) -> ClaimDetailOut:
    base = ClaimDetailOut.model_validate(claim)
    base.evidence_ids = [e.id for e in claim.evidence]
    base.event_ids = [
        row.event_id
        for row in db.scalars(select(ClaimEvent).where(ClaimEvent.claim_id == claim.id)).all()
    ]
    return base


@router.get("/cases/{case_id}/claims", response_model=ClaimListOut)
def list_claims(case_id: uuid.UUID, db: DbDep, user: CurrentUser) -> ClaimListOut:
    owned_case_or_404(db, case_id, user.id)
    rows = list(
        db.scalars(select(Claim).where(Claim.case_id == case_id).order_by(Claim.created_at.asc())).all()
    )
    return ClaimListOut(claims=[_detail_out(db, r) for r in rows], total=len(rows))


@router.post("/cases/{case_id}/claims", response_model=ClaimDetailOut, status_code=201)
def create_claim(case_id: uuid.UUID, body: ClaimCreate, db: DbDep, user: CurrentUser) -> ClaimDetailOut:
    case = owned_case_or_404(db, case_id, user.id)
    _validate_links(db, case.id, body.evidence_ids, body.event_ids)

    row = Claim(
        case_id=case.id,
        title=body.title,
        description=body.description,
        amount=body.amount,
        calculation=body.calculation,
        notes=body.notes,
        status=ClaimStatus.DRAFT,
    )
    db.add(row)
    db.flush()
    _set_evidence_links(db, row, body.evidence_ids)
    _set_event_links(db, row, body.event_ids)
    db.commit()
    db.refresh(row)
    audit(
        db,
        action=AuditAction.CLAIM_CREATED,
        user_id=user.id,
        case_id=case.id,
        entity_type="claim",
        entity_id=row.id,
        metadata={"title": row.title},
    )
    return _detail_out(db, row)


@router.get("/claims/{claim_id}", response_model=ClaimDetailOut)
def get_claim(claim_id: uuid.UUID, db: DbDep, user: CurrentUser) -> ClaimDetailOut:
    row = _get_owned_claim(db, user, claim_id)
    return _detail_out(db, row)


@router.patch("/claims/{claim_id}", response_model=ClaimDetailOut)
def update_claim(claim_id: uuid.UUID, body: ClaimUpdate, db: DbDep, user: CurrentUser) -> ClaimDetailOut:
    row = _get_owned_claim(db, user, claim_id)
    payload = body.model_dump(exclude_unset=True)
    evidence_ids = payload.pop("evidence_ids", None)
    event_ids = payload.pop("event_ids", None)

    if evidence_ids is not None or event_ids is not None:
        _validate_links(
            db,
            row.case_id,
            evidence_ids or [],
            event_ids or [],
        )

    for key, value in payload.items():
        setattr(row, key, value)
    if evidence_ids is not None:
        _set_evidence_links(db, row, evidence_ids)
    if event_ids is not None:
        _set_event_links(db, row, event_ids)
    db.commit()
    db.refresh(row)
    audit(
        db,
        action=AuditAction.CLAIM_UPDATED,
        user_id=user.id,
        case_id=row.case_id,
        entity_type="claim",
        entity_id=row.id,
        metadata={"fields": sorted(payload.keys())},
    )
    return _detail_out(db, row)


@router.delete("/claims/{claim_id}", status_code=204)
def delete_claim(claim_id: uuid.UUID, db: DbDep, user: CurrentUser) -> None:
    row = _get_owned_claim(db, user, claim_id)
    case_id = row.case_id
    title = row.title
    db.execute(delete(ClaimEvent).where(ClaimEvent.claim_id == row.id))
    db.delete(row)
    db.commit()
    audit(
        db,
        action=AuditAction.CLAIM_DELETED,
        user_id=user.id,
        case_id=case_id,
        entity_type="claim",
        metadata={"title": title},
    )
