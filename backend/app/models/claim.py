"""Claim — a factual assertion the user is trying to support."""

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
    from app.models.evidence import Evidence


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

    case: Mapped["Case"] = relationship()
    evidence: Mapped[list["Evidence"]] = relationship(
        secondary="evidence_claims", back_populates="claims", lazy="selectin"
    )
