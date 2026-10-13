"""Evidence gaps API routes (A3)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.deps import CurrentUser, DbDep
from app.models.case_gap import CaseEvidenceGapResult
from app.routes.cases import _get_owned
from app.schemas import (
    EvidenceGapHistoryOut,
    EvidenceGapResultOut,
    EvidenceGapTriggerOut,
)
from app.services import evidence_gaps as gaps_service

router = APIRouter(prefix="/cases")


@router.post("/{case_id}/evidence-gaps", response_model=EvidenceGapResultOut)
def trigger_evidence_gaps(
    case_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> EvidenceGapResultOut:
    _get_owned(db, user, case_id)
    try:
        res = gaps_service.analyze_evidence_gaps(db, case_id, user_id=user.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "GAP_ANALYSIS_FAILED", "message": str(e)},
        ) from e
    return EvidenceGapResultOut.model_validate(res)


@router.get("/{case_id}/evidence-gaps", response_model=EvidenceGapResultOut)
def get_latest_evidence_gaps(
    case_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> EvidenceGapResultOut:
    _get_owned(db, user, case_id)
    res = db.scalar(
        select(CaseEvidenceGapResult)
        .where(CaseEvidenceGapResult.case_id == case_id)
        .order_by(CaseEvidenceGapResult.version.desc())
        .limit(1)
    )
    if res is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "GAP_NOT_FOUND", "message": "No gap analysis found."},
        )
    return EvidenceGapResultOut.model_validate(res)


@router.get("/{case_id}/evidence-gaps/history", response_model=EvidenceGapHistoryOut)
def get_evidence_gaps_history(
    case_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> EvidenceGapHistoryOut:
    _get_owned(db, user, case_id)
    base = select(CaseEvidenceGapResult).where(CaseEvidenceGapResult.case_id == case_id)
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = db.scalars(
        base.order_by(CaseEvidenceGapResult.version.desc()).limit(limit).offset(offset)
    ).all()
    return EvidenceGapHistoryOut(
        results=[EvidenceGapResultOut.model_validate(r) for r in rows],
        total=total,
    )
