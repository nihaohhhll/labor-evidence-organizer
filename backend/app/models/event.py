"""Event model — a dated point on the case timeline."""

from __future__ import annotations

import uuid
from datetime import date, time
from typing import TYPE_CHECKING

from sqlalchemy import Date, Float, ForeignKey, Index, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UUID as PGUUID

from app.db import Base
from app.models.base import TimestampMixin, UUIDPk

if TYPE_CHECKING:
    from app.models.case import Case
    from app.models.evidence import Evidence


class Event(Base, UUIDPk, TimestampMixin):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_case_id_event_date", "case_id", "event_date"),)

    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    event_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    # "day" / "month" / "unknown" — timeline UI renders a placeholder instead
    # of a wrong date when precision is unknown.
    precision: Mapped[str] = mapped_column(
        String(16), nullable=False, default="day", server_default="day"
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="PENDING", server_default="PENDING"
    )
    # Events merged away point at the surviving event id.
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )

    case: Mapped["Case"] = relationship(back_populates="events")
    evidence: Mapped[list["Evidence"]] = relationship(
        secondary="evidence_events", back_populates="events", lazy="selectin"
    )
