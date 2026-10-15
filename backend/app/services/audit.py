"""Audit logging service (docs/05 audit_logs, docs/11 §9).

Records who did what to which case. Two rules make this safe:

1. **Redact before persist.** Metadata may contain a filename the user chose,
   which is routinely their own ID card scan. `redact_mapping` scrubs it.
2. **Never break the request.** An audit failure is logged and swallowed —
   losing an audit row is bad, but failing a user's upload because the audit
   insert threw would be worse.

The write is also deliberately *not* part of the caller's transaction: if the
caller rolls back, the audit row for the attempt should still exist.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.redaction import redact_mapping

logger = logging.getLogger(__name__)


class AuditAction:
    """Action names, kept as constants so queries cannot typo them."""

    CASE_CREATED = "case.created"
    CASE_UPDATED = "case.updated"
    CASE_DELETED = "case.deleted"
    FILE_UPLOADED = "file.uploaded"
    FILE_DELETED = "file.deleted"
    FILE_DOWNLOADED = "file.downloaded"
    FILE_RETRIED = "file.retried"
    ANALYSIS_RUN = "analysis.run"
    EVIDENCE_CONFIRMED = "evidence.confirmed"
    EVIDENCE_UPDATED = "evidence.updated"
    EVIDENCE_REANALYZED = "evidence.reanalyzed"
    REVIEW_CONFIRMED = "review.confirmed"
    REVIEW_DISCARDED = "review.discarded"
    EXPORT_CREATED = "export.created"
    EXPORT_DOWNLOADED = "export.downloaded"
    EXPORT_DELETED = "export.deleted"
    # Phase 9-A: arbitration material packages.
    MATERIAL_PACKAGE_CREATED = "material_package.created"
    MATERIAL_PACKAGE_UPDATED = "material_package.updated"
    MATERIAL_PACKAGE_ITEMS_SAVED = "material_package.items_saved"
    MATERIAL_PACKAGE_SNAPSHOT_CREATED = "material_package.snapshot_created"
    MATERIAL_PACKAGE_DELETED = "material_package.deleted"
    # Denying a request is itself security-relevant.
    ACCESS_DENIED = "access.denied"
    # Workbench phase: claims, trial prep.
    CLAIM_CREATED = "claim.created"
    CLAIM_UPDATED = "claim.updated"
    CLAIM_DELETED = "claim.deleted"
    TRIAL_PREP_UPDATED = "trial_prep.updated"


def record(
    db: Session,
    *,
    action: str,
    user_id: uuid.UUID | None = None,
    case_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> None:
    """Append one audit row. Never raises into the caller."""
    try:
        db.add(
            AuditLog(
                case_id=case_id,
                user_id=user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                metadata_json=redact_mapping(metadata) if metadata else None,
            )
        )
        # Commit independently of the caller's unit of work so the record
        # survives a later rollback.
        db.commit()
    except Exception:
        logger.exception("failed to write audit row action=%s", action)
        db.rollback()


def recent_for_case(db: Session, case_id: uuid.UUID, limit: int = 50) -> list[AuditLog]:
    """Newest-first audit trail for one case."""
    from sqlalchemy import select

    return list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.case_id == case_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        ).all()
    )
