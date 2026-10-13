"""ReviewItem — one pending AI-vs-user field decision."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, UUID as PGUUID

from app.db import Base
from app.models.base import TimestampMixin, UUIDPk

if TYPE_CHECKING:
    from app.models.case import Case


class ReviewStatusValue:
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    DISCARDED = "DISCARDED"


class ReviewItem(Base, UUIDPk, TimestampMixin):
    __tablename__ = "review_items"
    __table_args__ = (Index("ix_review_items_case_id_status", "case_id", "status"),)

    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # "evidence" | "event" | "person"
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    ai_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    user_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=ReviewStatusValue.PENDING,
        server_default="PENDING",
    )
    confidence: Mapped[float | None] = mapped_column(nullable=True)

    case: Mapped["Case"] = relationship()
