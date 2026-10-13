"""Case CRUD routes.

Every handler resolves the row through `_get_owned`, which filters on both
`id` and the caller's `user_id`, so one user can never read or mutate another
user's case (docs/11_SECURITY.md threat model: 越权读取其他案件).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select

from app.deps import CurrentUser, DbDep
from app.models.base import utcnow
from app.models.case import Case, CaseStatus
from app.models.evidence import Evidence
from app.services.audit import AuditAction, record as audit
from app.models.event import Event
from app.models.file import File
from app.schemas import CaseCreate, CaseDetailOut, CaseOut, CaseUpdate, Page

router = APIRouter(prefix="/cases")


def _get_owned(db, user, case_id: uuid.UUID) -> Case:
    """Fetch a case or raise 404.

    404 (not 403) is deliberate: a 403 would confirm that the id exists.
    """
    case = db.scalar(
        select(Case).where(Case.id == case_id, Case.user_id == user.id, Case.deleted_at.is_(None))
    )
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CASE_NOT_FOUND", "message": "Case not found."},
        )
    return case


def _counts(db, case_id: uuid.UUID) -> tuple[int, int, int]:
    file_count = db.scalar(
        select(func.count()).select_from(File).where(File.case_id == case_id, File.deleted_at.is_(None))
    )
    evidence_count = db.scalar(
        select(func.count()).select_from(Evidence).where(Evidence.case_id == case_id)
    )
    event_count = db.scalar(
        select(func.count()).select_from(Event).where(Event.case_id == case_id)
    )
    return int(file_count or 0), int(evidence_count or 0), int(event_count or 0)


def _detail(db, case: Case) -> CaseDetailOut:
    files, evidence, events = _counts(db, case.id)
    out = CaseDetailOut.model_validate(case)
    out.file_count = files
    out.evidence_count = evidence
    out.event_count = events
    return out


@router.post("", response_model=CaseDetailOut, status_code=status.HTTP_201_CREATED)
def create_case(body: CaseCreate, db: DbDep, user: CurrentUser) -> CaseDetailOut:
    case = Case(user_id=user.id, name=body.name, description=body.description)
    db.add(case)
    db.commit()
    db.refresh(case)
    audit(
        db,
        action=AuditAction.CASE_CREATED,
        user_id=user.id,
        case_id=case.id,
        entity_type="case",
        entity_id=case.id,
        metadata={"name": case.name},
    )
    return _detail(db, case)


@router.get("", response_model=Page)
def list_cases(
    db: DbDep,
    user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Page:
    base = select(Case).where(Case.user_id == user.id, Case.deleted_at.is_(None))
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = db.scalars(
        base.order_by(Case.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return Page(
        items=[CaseOut.model_validate(c) for c in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{case_id}", response_model=CaseDetailOut)
def get_case(case_id: uuid.UUID, db: DbDep, user: CurrentUser) -> CaseDetailOut:
    return _detail(db, _get_owned(db, user, case_id))


@router.patch("/{case_id}", response_model=CaseDetailOut)
def update_case(
    case_id: uuid.UUID, body: CaseUpdate, db: DbDep, user: CurrentUser
) -> CaseDetailOut:
    case = _get_owned(db, user, case_id)
    payload = body.model_dump(exclude_unset=True)
    changed = sorted(payload)
    for key, value in payload.items():
        setattr(case, key, value)
    db.commit()
    db.refresh(case)
    audit(
        db,
        action=AuditAction.CASE_UPDATED,
        user_id=user.id,
        case_id=case.id,
        entity_type="case",
        entity_id=case.id,
        metadata={"changed_fields": changed},
    )
    return _detail(db, case)


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case(case_id: uuid.UUID, db: DbDep, user: CurrentUser) -> Response:
    """Soft delete: the row stays for audit/restore (docs/05 soft delete)."""
    case = _get_owned(db, user, case_id)
    case.deleted_at = utcnow()
    db.commit()
    audit(
        db,
        action=AuditAction.CASE_DELETED,
        user_id=user.id,
        case_id=case.id,
        entity_type="case",
        entity_id=case.id,
        metadata={"name": case.name},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
