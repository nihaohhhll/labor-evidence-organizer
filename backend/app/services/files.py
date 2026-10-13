"""File service: upload, dedupe, soft delete, retry.

One place owns every rule about originals so the routes stay thin:
validation, SHA-256 dedupe, storage key construction and status transitions
all live here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.files.validation import UnsupportedFileType, validate_upload
from app.models.base import utcnow
from app.models.case import Case
from app.models.file import File, FileStatus
from app.storage import Storage, sha256_hex

# Statuses a file may legally move to. Enforced by `_transition` so a typo
# can never park a row in an unknown state.
# `FAILED` is genuinely terminal: it needs an explicit user retry before the
# file may be processed again (US B-05).
#
# `COMPLETED` is *not* terminal. docs/01 US D-04 and docs/12 Scenario 4 both
# require re-analysis to work, and docs/14 says a fresh analysis must produce
# a new version rather than be blocked. Treating COMPLETED as terminal would
# make "重新分析" impossible after the first success.
_FAILED_ONLY = {FileStatus.FAILED.value}


class FileServiceError(Exception):
    """Base error carrying a safe, user-facing message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class UploadOutcome:
    file: File
    created: bool  # False when an identical SHA-256 already existed


def _storage_key(case_id: uuid.UUID, sha256: str, filename: str) -> str:
    """Content-addressed key: immutable, collision-free and traversal-safe."""
    dot = filename.rfind(".")
    ext = filename[dot:].lower() if dot > 0 else ""
    return f"cases/{case_id}/originals/{sha256}{ext}"


def get_owned_case(db: Session, case_id: uuid.UUID, user_id: uuid.UUID) -> Case:
    """Resolve a case owned by `user_id` or raise (404 semantics)."""
    case = db.scalar(
        select(Case).where(
            Case.id == case_id, Case.user_id == user_id, Case.deleted_at.is_(None)
        )
    )
    if case is None:
        raise FileServiceError("CASE_NOT_FOUND", "Case not found.")
    return case


def get_owned_file(db: Session, file_id: uuid.UUID, user_id: uuid.UUID) -> File:
    """Resolve a file through its case, so ownership is always checked."""
    file = db.scalar(
        select(File)
        .join(Case, Case.id == File.case_id)
        .where(
            File.id == file_id,
            File.deleted_at.is_(None),
            Case.user_id == user_id,
            Case.deleted_at.is_(None),
        )
    )
    if file is None:
        raise FileServiceError("FILE_NOT_FOUND", "File not found.")
    return file


def upload_file(
    db: Session,
    storage: Storage,
    case: Case,
    filename: str,
    data: bytes,
    *,
    mime_override: str | None = None,
) -> UploadOutcome:
    """Validate, dedupe and persist one uploaded original.

    The bytes are written before the row is committed; if the commit fails the
    orphan object is removed so storage does not drift from the database.
    """
    try:
        mime = validate_upload(filename, data)
    except UnsupportedFileType as exc:
        raise FileServiceError("UNSUPPORTED_FILE", str(exc)) from None

    digest = sha256_hex(data)

    existing = db.scalar(
        select(File).where(
            File.case_id == case.id,
            File.sha256 == digest,
            File.deleted_at.is_(None),
        )
    )
    if existing is not None:
        # Same bytes already in this case: return it instead of duplicating.
        return UploadOutcome(file=existing, created=False)

    key = _storage_key(case.id, digest, filename)
    storage.put(key, data)

    row = File(
        case_id=case.id,
        original_filename=filename,
        mime_type=mime_override or mime,
        size=len(data),
        sha256=digest,
        storage_key=key,
        status=FileStatus.UPLOADED.value,
    )
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(key)  # keep storage and DB consistent
        raise
    db.refresh(row)
    return UploadOutcome(file=row, created=True)


def _transition(file: File, target: FileStatus) -> None:
    """Move a file to `target`, refusing to resurrect a failed state."""
    if file.status in _FAILED_ONLY and target is not FileStatus.QUEUED:
        raise FileServiceError(
            "INVALID_TRANSITION",
            f"文件已失败（{file.status}），需要先重试再处理。",
        )
    file.status = target.value


def mark_processing(db: Session, file: File) -> None:
    _transition(file, FileStatus.PROCESSING)
    db.commit()


def mark_review_required(db: Session, file: File) -> None:
    _transition(file, FileStatus.REVIEW_REQUIRED)
    db.commit()


def mark_completed(db: Session, file: File) -> None:
    _transition(file, FileStatus.COMPLETED)
    file.error_message = None
    db.commit()


def mark_failed(db: Session, file: File, message: str) -> None:
    file.status = FileStatus.FAILED.value
    file.error_message = message[:1024]
    db.commit()


def retry_file(db: Session, file: File) -> File:
    """Put a FAILED file back into the queue (US B-05 失败重试)."""
    if file.status != FileStatus.FAILED.value:
        raise FileServiceError(
            "NOT_FAILED", "只有失败的文件才能重试。"
        )
    file.status = FileStatus.QUEUED.value
    file.error_message = None
    db.commit()
    db.refresh(file)
    return file


def soft_delete_file(db: Session, file: File) -> None:
    """Soft delete. The original object is kept for audit/restore."""
    file.deleted_at = utcnow()
    db.commit()


def list_files(db: Session, case_id: uuid.UUID, *, include_deleted: bool = False) -> list[File]:
    stmt = select(File).where(File.case_id == case_id)
    if not include_deleted:
        stmt = stmt.where(File.deleted_at.is_(None))
    return list(db.scalars(stmt.order_by(File.created_at.asc())).all())


def count_by_status(db: Session, case_id: uuid.UUID) -> dict[str, int]:
    rows = db.execute(
        select(File.status, func.count())
        .where(File.case_id == case_id, File.deleted_at.is_(None))
        .group_by(File.status)
    ).all()
    return {status: int(count) for status, count in rows}
