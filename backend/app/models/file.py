"""File model — one row per uploaded original document.

`storage_key` points at the immutable original; nothing in the system ever
rewrites the bytes behind this key (docs/14_AI_CODING_AGENT_RULES.md).
"""

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UUID as PGUUID

from app.db import Base
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDPk

if TYPE_CHECKING:
    from app.models.analysis import DocumentAnalysis
    from app.models.case import Case
    from app.models.evidence import Evidence


class FileStatus(str, enum.Enum):
    """Processing lifecycle required by docs/03_FUNCTIONAL_SPEC.md §3."""

    UPLOADED = "UPLOADED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class File(Base, UUIDPk, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "files"
    __table_args__ = (
        Index("ix_files_case_id_sha256", "case_id", "sha256"),
        Index("ix_files_case_id_status", "case_id", "status"),
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=FileStatus.UPLOADED.value,
        server_default=FileStatus.UPLOADED.value,
    )
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    case: Mapped["Case"] = relationship(back_populates="files")
    analyses: Mapped[list["DocumentAnalysis"]] = relationship(
        back_populates="file", cascade="all, delete-orphan", lazy="selectin"
    )
    evidence: Mapped[list["Evidence"]] = relationship(
        back_populates="source_file", lazy="selectin"
    )
