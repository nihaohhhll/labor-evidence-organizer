"""AuditLog — append-only record of significant actions."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, UUID as PGUUID

from app.db import Base
from app.models.base import TimestampMixin, UUIDPk

if TYPE_CHECKING:
    from app.models.case import Case


class AuditLog(Base, UUIDPk, TimestampMixin):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_case_id_created_at", "case_id", "created_at"),)

    case_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    # Metadata must never contain full ID numbers or bank accounts — see
    # docs/11_SECURITY.md log-masking rule.
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
