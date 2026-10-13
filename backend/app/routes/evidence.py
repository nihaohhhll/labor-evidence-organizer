"""Evidence CRUD routes (docs/06_API_SPEC Evidence section)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from app.deps import CurrentUser, DbDep, owned_case_or_404, owned_file_or_404
from app.services.audit import AuditAction, record as audit
from app.models.evidence import Evidence
from app.schemas import (
    EvidenceConfirmOut,
    EvidenceCreate,
    EvidenceDetailOut,
    EvidenceListOut,
    EvidenceUpdate,
)
from app.services import analysis as analysis_service
from app.services import files as file_service
from sqlalchemy import select

router = APIRouter()


def _get_owned_evidence(db, user, evidence_id: uuid.UUID) -> Evidence:
    row = db.scalar(select(Evidence).where(Evidence.id == evidence_id))
    if row is None:
        raise HTTPException(
            404, detail={"code": "EVIDENCE_NOT_FOUND", "message": "Evidence not found."}
        )
    # Ownership is enforced through the owning case; a foreign case raises 404.
    owned_case_or_404(db, row.case_id, user.id)
    return row


@router.get("/cases/{case_id}/evidence", response_model=EvidenceListOut)
def list_evidence(
    case_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    review_status: str | None = Query(default=None),
) -> EvidenceListOut:
    case = owned_case_or_404(db, case_id, user.id)

    stmt = select(Evidence).where(Evidence.case_id == case.id)
    if review_status:
        stmt = stmt.where(Evidence.review_status == review_status)
    rows = list(db.scalars(stmt.order_by(Evidence.evidence_number.asc())).all())
    return EvidenceListOut(
        evidence=[EvidenceDetailOut.model_validate(r) for r in rows],
        total=len(rows),
    )


@router.post("/cases/{case_id}/evidence", response_model=EvidenceDetailOut, status_code=201)
def create_evidence(
    case_id: uuid.UUID, body: EvidenceCreate, db: DbDep, user: CurrentUser
) -> EvidenceDetailOut:
    """Manually add evidence; the number is always allocated by the server."""
    case = owned_case_or_404(db, case_id, user.id)

    row = Evidence(
        case_id=case.id,
        source_file_id=body.source_file_id,
        evidence_number=analysis_service.next_evidence_number(db, case.id),
        title=body.title,
        category=body.category,
        event_date=body.event_date,
        summary=body.summary,
        proof_purpose=body.proof_purpose,
        confidence=None,
        review_status="CONFIRMED" if body.confirm_now else "PENDING",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return EvidenceDetailOut.model_validate(row)


@router.get("/evidence/{evidence_id}", response_model=EvidenceDetailOut)
def get_evidence(evidence_id: uuid.UUID, db: DbDep, user: CurrentUser) -> EvidenceDetailOut:
    return EvidenceDetailOut.model_validate(_get_owned_evidence(db, user, evidence_id))


@router.patch("/evidence/{evidence_id}", response_model=EvidenceDetailOut)
def update_evidence(
    evidence_id: uuid.UUID, body: EvidenceUpdate, db: DbDep, user: CurrentUser
) -> EvidenceDetailOut:
    """Edit a field. Edited field names are remembered so a later re-analysis
    can never silently overwrite the human's value (docs/14 用户修改优先)."""
    row = _get_owned_evidence(db, user, evidence_id)
    payload = body.model_dump(exclude_unset=True)
    for key, value in payload.items():
        setattr(row, key, value)
        if key in ("title", "category", "event_date", "summary", "proof_purpose"):
            row.mark_edited(key)
    db.commit()
    db.refresh(row)
    audit(
        db,
        action=AuditAction.EVIDENCE_UPDATED,
        user_id=user.id,
        case_id=row.case_id,
        entity_type="evidence",
        entity_id=row.id,
        # Field *names* only — the values may contain bank details.
        metadata={"edited_fields": sorted(row.edited_fields)},
    )
    return EvidenceDetailOut.model_validate(row)


@router.post("/evidence/{evidence_id}/confirm", response_model=EvidenceConfirmOut)
def confirm_evidence(
    evidence_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> EvidenceConfirmOut:
    row = _get_owned_evidence(db, user, evidence_id)
    row.review_status = "CONFIRMED"
    db.commit()
    audit(
        db,
        action=AuditAction.EVIDENCE_CONFIRMED,
        user_id=user.id,
        case_id=row.case_id,
        entity_type="evidence",
        entity_id=row.id,
    )
    return EvidenceConfirmOut(id=row.id, review_status=row.review_status)


@router.delete("/evidence/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_evidence(evidence_id: uuid.UUID, db: DbDep, user: CurrentUser) -> Response:
    row = _get_owned_evidence(db, user, evidence_id)
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/evidence/{evidence_id}/reanalyze", response_model=EvidenceDetailOut)
def reanalyze_evidence(
    evidence_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> EvidenceDetailOut:
    """Re-run analysis on the source file and merge into this evidence.

    Any field the user has already edited is preserved — a new AI value is
    stored on the analysis row, not on the user's row.
    """
    row = _get_owned_evidence(db, user, evidence_id)
    protected = set(row.edited_fields)

    if row.source_file_id is None:
        raise HTTPException(
            409, detail={"code": "NO_SOURCE_FILE", "message": "该证据没有关联原始文件。"}
        )

    file = owned_file_or_404(db, row.source_file_id, user.id)
    try:
        analysis = analysis_service.analyze_file(db, file)
    except analysis_service.AnalysisError as exc:
        raise HTTPException(422, detail={"code": exc.code, "message": exc.message})

    structured = analysis.structured_json or {}
    mapping = {
        "summary": structured.get("summary"),
        "proof_purpose": structured.get("proof_purpose"),
    }
    for field_name, new_value in mapping.items():
        if new_value and field_name not in protected:
            setattr(row, field_name, new_value)

    row.analysis_id = analysis.id
    row.confidence = analysis.confidence
    db.commit()
    db.refresh(row)
    audit(
        db,
        action=AuditAction.EVIDENCE_REANALYZED,
        user_id=user.id,
        case_id=row.case_id,
        entity_type="evidence",
        entity_id=row.id,
        # Proves the protection actually held on this run.
        metadata={"protected_fields": sorted(protected)},
    )
    return EvidenceDetailOut.model_validate(row)
