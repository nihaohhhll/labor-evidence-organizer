"""File upload / listing / download routes.

Multipart parsing lives here, but every rule (validation, dedupe, ownership)
is enforced in `app.services.files` so it also holds for non-HTTP callers.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from fastapi import Form
from sqlalchemy.orm import Session

from app.deps import CurrentUser, DbDep, owned_case_or_404, owned_file_or_404
from app.config import settings
from app.models.file import File as FileRow
from app.schemas import FileDetailOut, FileListOut, UploadOutcomeOut
from app.services import files as file_service
from app.http_headers import nosniff_private_headers
from app.services.audit import AuditAction, record as audit
from app.storage import get_storage

router = APIRouter()


def _read_upload(upload: UploadFile) -> bytes:
    """Read an upload part, refusing to buffer more than the configured cap.

    The limit is read from `settings` at call time (not frozen into a module
    constant) so tests and deployments can change it without a restart.
    Reading with a cap rather than trusting Content-Length also stops a client
    from filling memory by lying about the size.
    """
    limit = settings.max_upload_bytes
    data = upload.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={"code": "FILE_TOO_LARGE", "message": "文件超过大小上限。"},
        )
    return data


def _to_detail(row: FileRow) -> FileDetailOut:
    out = FileDetailOut.model_validate(row)
    out.download_url = f"/api/v1/files/{row.id}/content"
    return out


@router.post(
    "/cases/{case_id}/files",
    response_model=UploadOutcomeOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_files(
    case_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    files: list[UploadFile] = File(..., description="可一次提交多个文件"),
) -> UploadOutcomeOut:
    """Batch upload. A single bad file must not abort the whole batch (US-002)."""
    case = owned_case_or_404(db, case_id, user.id)

    storage = get_storage()
    created: list[FileDetailOut] = []
    skipped: list[dict[str, str]] = []

    for upload in files:
        name = upload.filename or ""
        try:
            data = _read_upload(upload)
            outcome = file_service.upload_file(db, storage, case, name, data)
        except HTTPException as exc:
            skipped.append({"filename": name, "reason": exc.detail["message"]})
            continue
        except file_service.FileServiceError as exc:
            skipped.append({"filename": name, "reason": exc.message})
            continue
        if outcome.created:
            created.append(_to_detail(outcome.file))
            audit(
                db,
                action=AuditAction.FILE_UPLOADED,
                user_id=user.id,
                case_id=case.id,
                entity_type="file",
                entity_id=outcome.file.id,
                # Filename is user-controlled and may be their own ID scan,
                # so it is redacted before it is persisted.
                metadata={
                    "filename": name,
                    "size": outcome.file.size,
                    "mime_type": outcome.file.mime_type,
                },
            )

    return UploadOutcomeOut(files=created, skipped=skipped)


@router.get("/cases/{case_id}/files", response_model=FileListOut)
def list_case_files(
    case_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> FileListOut:
    case = owned_case_or_404(db, case_id, user.id)
    rows = file_service.list_files(db, case.id)
    return FileListOut(
        files=[_to_detail(r) for r in rows],
        status_counts=file_service.count_by_status(db, case.id),
    )


@router.get("/files/{file_id}", response_model=FileDetailOut)
def get_file(file_id: uuid.UUID, db: DbDep, user: CurrentUser) -> FileDetailOut:
    return _to_detail(owned_file_or_404(db, file_id, user.id))


@router.get("/files/{file_id}/content")
def download_file(file_id: uuid.UUID, db: DbDep, user: CurrentUser) -> Response:
    """Serve the immutable original.

    Authorization is checked against the owning case; the stored key is never
    taken from the request, so a crafted path cannot reach another case.
    """
    row = owned_file_or_404(db, file_id, user.id)

    # Downloads are recorded: this is the trail that shows who saw which
    # original document.
    audit(
        db,
        action=AuditAction.FILE_DOWNLOADED,
        user_id=user.id,
        case_id=row.case_id,
        entity_type="file",
        entity_id=row.id,
        metadata={"filename": row.original_filename},
    )

    try:
        data = get_storage().get(row.storage_key)
    except FileNotFoundError:
        raise HTTPException(
            410, detail={"code": "CONTENT_MISSING", "message": "原始文件已不存在。"}
        ) from None

    # Prevent the browser from sniffing uploaded content into HTML/JS. The
    # filename may be Chinese, so it goes through RFC 5987 encoding.
    return Response(
        content=data,
        media_type=row.mime_type,
        headers=nosniff_private_headers(row.original_filename, inline=True),
    )


@router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(file_id: uuid.UUID, db: DbDep, user: CurrentUser) -> Response:
    row = owned_file_or_404(db, file_id, user.id)
    file_service.soft_delete_file(db, row)
    audit(
        db,
        action=AuditAction.FILE_DELETED,
        user_id=user.id,
        case_id=row.case_id,
        entity_type="file",
        entity_id=row.id,
        metadata={"filename": row.original_filename},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/files/{file_id}/retry", response_model=FileDetailOut)
def retry_file(file_id: uuid.UUID, db: DbDep, user: CurrentUser) -> FileDetailOut:
    row = owned_file_or_404(db, file_id, user.id)
    try:
        row = file_service.retry_file(db, row)
    except file_service.FileServiceError as exc:
        raise HTTPException(409, detail={"code": exc.code, "message": exc.message})
    audit(
        db,
        action=AuditAction.FILE_RETRIED,
        user_id=user.id,
        case_id=row.case_id,
        entity_type="file",
        entity_id=row.id,
    )
    return _to_detail(row)
