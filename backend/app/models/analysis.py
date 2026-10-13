"""DocumentAnalysis — immutable AI output for one file.

Append only: a re-analysis inserts a new row rather than editing an old one,
so provider/model/prompt_version history stays intact
(docs/04_TECH_ARCHITECTURE.md rule 5).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, UUID as PGUUID

from app.db import Base
from app.models.base import TimestampMixin, UUIDPk

if TYPE_CHECKING:
    from app.models.file import File


class DocumentAnalysis(Base, UUIDPk, TimestampMixin):
    __tablename__ = "document_analyses"
    __table_args__ = (Index("ix_document_analyses_file_id_created_at", "file_id", "created_at"),)

    file_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    classification: Mapped[str | None] = mapped_column(String(64), nullable=True)
    classification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="SUCCESS", server_default="SUCCESS"
    )
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    file: Mapped["File"] = relationship(back_populates="analyses")
