"""ExportJob — an async document generation request."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UUID as PGUUID

from app.db import Base
from app.models.base import TimestampMixin, UUIDPk

if TYPE_CHECKING:
    from app.models.case import Case
    from app.models.material_package import MaterialPackage, MaterialPackageSnapshot


class ExportStatus:
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ExportFormat:
    DOCX = "docx"
    PDF = "pdf"
    ZIP = "zip"


class ExportJob(Base, UUIDPk, TimestampMixin):
    __tablename__ = "export_jobs"
    __table_args__ = (Index("ix_export_jobs_case_id_status", "case_id", "status"),)

    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=ExportStatus.QUEUED, server_default="QUEUED"
    )
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Phase 9-C: package exports are bound to one immutable snapshot so the
    # artifact can never be re-derived from a later draft. All nullable —
    # case-wide exports (Phase 7) leave them NULL.
    package_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("material_packages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("material_package_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )
    snapshot_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    include_gap_appendix: Mapped[bool] = mapped_column(
        # sa.text so DDL renders `DEFAULT false` (bare keyword) — valid on
        # PostgreSQL and SQLite alike; a quoted 'false' literal would be
        # stored as text by SQLite's boolean affinity.
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    gap_result_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("case_evidence_gap_results.id", ondelete="SET NULL"),
        nullable=True,
    )

    case: Mapped["Case"] = relationship()
    package: Mapped["MaterialPackage | None"] = relationship()
    snapshot: Mapped["MaterialPackageSnapshot | None"] = relationship()
