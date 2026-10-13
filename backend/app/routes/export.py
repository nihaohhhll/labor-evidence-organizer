"""Export routes: generate and download the evidence bundle.

Exports read only confirmed / user-reviewed data, and the produced artifact
is immutable once written (docs/10_DOCUMENT_GENERATION).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.deps import CurrentUser, DbDep, owned_case_or_404
from app.models.evidence import Evidence
from app.models.event import Event
from app.models.material_package import MaterialPackage
from app.schemas import ExportCreateIn, ExportJobOut, ExportListOut
from app.services import files as file_service
from app.http_headers import nosniff_private_headers
from app.services.audit import AuditAction, record as audit
from app.services.export import (
    EXPORT_FORMATS,
    ExportError,
    build_export,
    export_filename,
    package_export_filename,
)
from app.storage import get_storage

router = APIRouter()


def _get_owned_export(db, user, export_id: uuid.UUID):
    from app.models.export import ExportJob

    job = db.get(ExportJob, export_id)
    if job is None:
        raise HTTPException(404, detail={"code": "EXPORT_NOT_FOUND", "message": "Export not found."})
    owned_case_or_404(db, job.case_id, user.id)
    return job


@router.post("/cases/{case_id}/exports", response_model=ExportJobOut, status_code=201)
def create_export(
    case_id: uuid.UUID, body: ExportCreateIn, db: DbDep, user: CurrentUser
) -> ExportJobOut:
    case = owned_case_or_404(db, case_id, user.id)

    fmt = body.format.lower()
    if fmt not in EXPORT_FORMATS:
        raise HTTPException(
            422,
            detail={
                "code": "UNSUPPORTED_FORMAT",
                "message": f"不支持的导出格式：{body.format}",
            },
        )

    evidence = list(
        db.scalars(
            select(Evidence)
            .where(Evidence.case_id == case.id, Evidence.review_status == "CONFIRMED")
            .order_by(Evidence.evidence_number.asc())
        ).all()
    )
    events = list(
        db.scalars(
            select(Event)
            .where(Event.case_id == case.id, Event.merged_into_id.is_(None))
            .order_by(Event.event_date.asc().nulls_last())
        ).all()
    )

    if not evidence and not events:
        raise HTTPException(
            409,
            detail={"code": "NOTHING_TO_EXPORT", "message": "没有已确认的证据或事件可供导出。"},
        )

    try:
        job = build_export(db, case, fmt, evidence=evidence, events=events)
    except ExportError as exc:
        raise HTTPException(422, detail={"code": exc.code, "message": exc.message})

    _audit_export_created(db, user, case, job)
    return ExportJobOut.model_validate(job)


def _audit_export_created(db, user, case, job) -> None:
    audit(
        db,
        action=AuditAction.EXPORT_CREATED,
        user_id=user.id,
        case_id=case.id,
        entity_type="export",
        entity_id=job.id,
        metadata={"format": job.format, "status": job.status},
    )


@router.get("/cases/{case_id}/exports", response_model=ExportListOut)
def list_exports(case_id: uuid.UUID, db: DbDep, user: CurrentUser) -> ExportListOut:
    from app.models.export import ExportJob

    case = owned_case_or_404(db, case_id, user.id)

    rows = list(
        db.scalars(
            select(ExportJob)
            .where(ExportJob.case_id == case.id)
            .order_by(ExportJob.created_at.desc())
        ).all()
    )
    return ExportListOut(exports=[ExportJobOut.model_validate(r) for r in rows], total=len(rows))


@router.get("/exports/{export_id}", response_model=ExportJobOut)
def get_export(export_id: uuid.UUID, db: DbDep, user: CurrentUser) -> ExportJobOut:
    return ExportJobOut.model_validate(_get_owned_export(db, user, export_id))


@router.get("/exports/{export_id}/download")
def download_export(export_id: uuid.UUID, db: DbDep, user: CurrentUser) -> Response:
    job = _get_owned_export(db, user, export_id)

    if job.status != "COMPLETED" or not job.storage_key:
        raise HTTPException(
            409, detail={"code": "EXPORT_NOT_READY", "message": "导出尚未完成。"}
        )

    try:
        data = get_storage().get(job.storage_key)
    except FileNotFoundError:
        raise HTTPException(
            410, detail={"code": "EXPORT_MISSING", "message": "导出文件已不存在。"}
        ) from None

    case = owned_case_or_404(db, job.case_id, user.id)
    if job.package_id:
        # Phase 9-C: volume filename comes from the package, not the case.
        pkg = db.get(MaterialPackage, job.package_id)
        filename = package_export_filename(pkg.name if pkg else case.name, job.format)
    else:
        filename = export_filename(case.name, job.format)

    # Downloading a bundle is recorded: it is the trail that shows who took
    # the evidence package out of the system.
    audit(
        db,
        action=AuditAction.EXPORT_DOWNLOADED,
        user_id=user.id,
        case_id=case.id,
        entity_type="export",
        entity_id=job.id,
        metadata={"format": job.format},
    )

    media = {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pdf": "application/pdf",
        "zip": "application/zip",
    }.get(job.format, "application/octet-stream")

    return Response(
        content=data,
        media_type=media,
        headers=nosniff_private_headers(filename),
    )
