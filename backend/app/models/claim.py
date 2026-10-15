"""Claim — an arbitration request the user is building a case for.

Phase 10 (workbench): extended with amount / calculation / status so the
"仲裁请求 → 相关事实 → 证据 → 计算依据" view has real fields to show.
All new columns are nullable — existing rows stay valid.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UUID as PGUUID

from app.db import Base
from app.models.base import TimestampMixin, UUIDPk

if TYPE_CHECKING:
    from app.models.case import Case
    from app.models.event import Event
    from app.models.evidence import Evidence


class ClaimStatus:
    """Draft vs user-confirmed — never auto-promoted by AI."""

    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"


class Claim(Base, UUIDPk, TimestampMixin):
    __tablename__ = "claims"

    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Kept as free text so "12,345.67 元"、"约 3 个月工资" survives exactly
    # as typed — no float rounding, no invented precision.
    amount: Mapped[str | None] = mapped_column(String(64), nullable=True)
    calculation: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ClaimStatus.DRAFT, server_default=ClaimStatus.DRAFT
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    case: Mapped["Case"] = relationship()
    evidence: Mapped[list["Evidence"]] = relationship(
        secondary="evidence_claims", back_populates="claims", lazy="selectin"
    )
    events: Mapped[list["Event"]] = relationship(
        secondary="claim_events", lazy="selectin"
    )


class ClaimEvent(Base):
    """claim ↔ event join — a request's supporting facts."""

    __tablename__ = "claim_events"

    claim_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), primary_key=True
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
