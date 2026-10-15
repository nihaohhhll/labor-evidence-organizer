"""Case CRUD routes.

Every handler resolves the row through `_get_owned`, which filters on both
`id` and the caller's `user_id`, so one user can never read or mutate another
user's case (docs/11_SECURITY.md threat model: 越权读取其他案件).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select

from app.deps import CurrentUser, DbDep
from app.models.base import utcnow
from app.models.audit import AuditLog
from app.models.case import Case, CaseStatus
from app.models.claim import Claim
from app.models.evidence import Evidence
from app.models.material_package import MaterialPackage
from app.models.review import ReviewItem, ReviewStatusValue
from app.models.export import ExportJob, ExportStatus
from app.services.audit import AuditAction, record as audit
from app.models.event import Event
from app.models.file import File, FileStatus
from app.schemas import (
    AuditLogListOut,
    AuditLogOut,
    CaseCreate,
    CaseDetailOut,
    CaseNarrativeOut,
    CaseOut,
    CaseUpdate,
    Page,
    ProgressOut,
    ProgressTaskOut,
    TrialPrepOut,
    TrialPrepUpdate,
)
from app.services import narrative as narrative_service
from app.services import workbench as workbench_service

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
    claim_count = int(
        db.scalar(select(func.count()).select_from(Claim).where(Claim.case_id == case.id)) or 0
    )
    out = CaseDetailOut.model_validate(case)
    out.file_count = files
    out.evidence_count = evidence
    out.event_count = events
    out.claim_count = claim_count
    out.trial_prep = case.trial_prep
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


@router.post("/{case_id}/narrative", response_model=CaseNarrativeOut)
def generate_narrative(case_id: uuid.UUID, db: DbDep, user: CurrentUser) -> CaseNarrativeOut:
    """Draft a case narrative from analyzed materials.

    Deliberately a plain `def`: the LLM call runs `asyncio.run` inside the
    worker thread (same contract as routes/analysis.py). The result is NOT
    persisted — the client fills the textarea and the user saves it, so an AI
    draft can never silently overwrite a human-written account.
    """
    case = _get_owned(db, user, case_id)
    try:
        text, provider, model = narrative_service.generate_case_narrative(db, case)
    except narrative_service.NarrativeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": exc.message},
        )
    return CaseNarrativeOut(narrative=text, provider=provider, model=model)


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


# ---------- workbench: progress / trial prep / audit ----------


def _progress_counts(db, case_id: uuid.UUID) -> dict[str, int]:
    """Aggregate counts the progress derivation needs (single round-trip each)."""

    def _c(stmt) -> int:
        return int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)

    files_total = _c(select(File.id).where(File.case_id == case_id, File.deleted_at.is_(None)))
    files_ready = _c(
        select(File.id).where(
            File.case_id == case_id,
            File.deleted_at.is_(None),
            File.status.in_([FileStatus.COMPLETED.value, FileStatus.REVIEW_REQUIRED.value]),
        )
    )
    files_processing = _c(
        select(File.id).where(
            File.case_id == case_id,
            File.deleted_at.is_(None),
            File.status.in_(
                [FileStatus.UPLOADED.value, FileStatus.QUEUED.value, FileStatus.PROCESSING.value]
            ),
        )
    )
    files_failed = _c(
        select(File.id).where(
            File.case_id == case_id, File.deleted_at.is_(None), File.status == FileStatus.FAILED.value
        )
    )
    review_pending = _c(
        select(ReviewItem.id).where(
            ReviewItem.case_id == case_id, ReviewItem.status == ReviewStatusValue.PENDING
        )
    )
    evidence_total = _c(select(Evidence.id).where(Evidence.case_id == case_id))
    evidence_pending = _c(
        select(Evidence.id).where(Evidence.case_id == case_id, Evidence.review_status == "PENDING")
    )
    evidence_confirmed = _c(
        select(Evidence.id).where(Evidence.case_id == case_id, Evidence.review_status == "CONFIRMED")
    )
    events_total = _c(
        select(Event.id).where(Event.case_id == case_id, Event.merged_into_id.is_(None))
    )
    events_pending = _c(
        select(Event.id).where(
            Event.case_id == case_id,
            Event.merged_into_id.is_(None),
            Event.review_status == "PENDING",
        )
    )
    events_confirmed = _c(
        select(Event.id).where(
            Event.case_id == case_id,
            Event.merged_into_id.is_(None),
            Event.review_status == "CONFIRMED",
        )
    )
    claims_total = _c(select(Claim.id).where(Claim.case_id == case_id))
    # A claim is "unlinked" when it has neither supporting evidence nor a fact.
    from app.models.claim import ClaimEvent

    unlinked_sub = (
        select(Claim.id)
        .where(Claim.case_id == case_id)
        .where(~Claim.evidence.any())
        .where(~Claim.id.in_(select(ClaimEvent.claim_id)))
    )
    claims_unlinked = _c(unlinked_sub)
    packages_total = _c(
        select(MaterialPackage.id).where(MaterialPackage.case_id == case_id)
    )
    exports_done = _c(
        select(ExportJob.id).where(
            ExportJob.case_id == case_id, ExportJob.status == ExportStatus.COMPLETED
        )
    )
    return {
        "files_total": files_total,
        "files_ready": files_ready,
        "files_processing": files_processing,
        "files_failed": files_failed,
        "review_pending": review_pending,
        "evidence_total": evidence_total,
        "evidence_pending": evidence_pending,
        "evidence_confirmed": evidence_confirmed,
        "events_total": events_total,
        "events_pending": events_pending,
        "events_confirmed": events_confirmed,
        "claims_total": claims_total,
        "claims_unlinked": claims_unlinked,
        "packages_total": packages_total,
        "exports_done": exports_done,
    }


@router.get("/{case_id}/progress", response_model=ProgressOut)
def get_progress(case_id: uuid.UUID, db: DbDep, user: CurrentUser) -> ProgressOut:
    """Derived stage + task list. Pure computation — no writes, no invented data."""
    case = _get_owned(db, user, case_id)
    counts = _progress_counts(db, case.id)
    derived = workbench_service.derive_progress(
        counts, case_status=case.status, trial_prep=case.trial_prep
    )
    return ProgressOut(
        case_id=case.id,
        stage=derived["stage"],
        stage_label=derived["stage_label"],
        counts=counts,
        tasks=[ProgressTaskOut(**t) for t in derived["tasks"]],
        next_action_href=derived["next_action_href"],
    )


def _trial_prep_out(case: Case) -> TrialPrepOut:
    raw = case.trial_prep or {}
    known = {item_id for item_id, _ in workbench_service.TRIAL_CHECKLIST}
    checklist = {
        k: bool(v) for k, v in (raw.get("checklist") or {}).items() if k in known
    }
    return TrialPrepOut(
        hearing_date=raw.get("hearing_date"),
        hearing_note=raw.get("hearing_note"),
        mediation_note=raw.get("mediation_note"),
        ruling_note=raw.get("ruling_note"),
        checklist=checklist,
        updated_at=case.updated_at,
    )


@router.get("/{case_id}/trial-prep", response_model=TrialPrepOut)
def get_trial_prep(case_id: uuid.UUID, db: DbDep, user: CurrentUser) -> TrialPrepOut:
    case = _get_owned(db, user, case_id)
    return _trial_prep_out(case)


@router.patch("/{case_id}/trial-prep", response_model=TrialPrepOut)
def update_trial_prep(
    case_id: uuid.UUID, body: TrialPrepUpdate, db: DbDep, user: CurrentUser
) -> TrialPrepOut:
    case = _get_owned(db, user, case_id)
    payload = body.model_dump(exclude_unset=True)
    merged = dict(case.trial_prep or {})
    for key, value in payload.items():
        if key == "hearing_date":
            merged[key] = value.isoformat() if value is not None else None
        elif key == "checklist" and value is not None:
            # Partial updates merge per-item; an empty dict still clears.
            current = dict(merged.get("checklist") or {})
            current.update(value)
            merged[key] = current
        else:
            merged[key] = value
    case.trial_prep = merged
    db.commit()
    db.refresh(case)
    audit(
        db,
        action=AuditAction.TRIAL_PREP_UPDATED,
        user_id=user.id,
        case_id=case.id,
        entity_type="case",
        entity_id=case.id,
        metadata={"changed_fields": sorted(payload)},
    )
    return _trial_prep_out(case)


@router.get("/{case_id}/audit", response_model=AuditLogListOut)
def list_case_audit(
    case_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
) -> AuditLogListOut:
    """Recent significant actions for this case (workbench 首页/归档).

    metadata was redacted at write time (docs/11 log-masking) and never
    contains full ID numbers or bank accounts.
    """
    case = _get_owned(db, user, case_id)
    base = select(AuditLog).where(AuditLog.case_id == case.id)
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = list(db.scalars(base.order_by(AuditLog.created_at.desc()).limit(limit)).all())
    return AuditLogListOut(
        items=[AuditLogOut.model_validate(r) for r in rows],
        total=total,
    )
