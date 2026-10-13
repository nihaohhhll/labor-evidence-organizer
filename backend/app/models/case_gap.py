"""CaseEvidenceGapResult — evidence gaps analysis results.

Immutable per version: each re-analysis inserts a new row rather than editing.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, UUID as PGUUID

from app.db import Base
from app.models.base import TimestampMixin, UUIDPk

if TYPE_CHECKING:
    from app.models.case import Case
    from app.models.user import User


class CaseEvidenceGapResult(Base, UUIDPk, TimestampMixin):
    __tablename__ = "case_evidence_gap_results"
    __table_args__ = (
        UniqueConstraint("case_id", "version", name="uq_gap_case_version"),
        CheckConstraint("version > 0", name="ck_gap_version_positive"),
        Index("ix_gap_case_id_created_at", "case_id", "created_at"),
        Index("ix_case_evidence_gap_results_case_id", "case_id"),
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    gap_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    case: Mapped["Case"] = relationship(back_populates="gap_results")
    creator = relationship("User")
