"""Evidence, Person and the join tables linking them to events/claims."""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, UUID as PGUUID

from app.db import Base
from app.models.base import TimestampMixin, UUIDPk

if TYPE_CHECKING:
    from app.models.case import Case
    from app.models.claim import Claim
    from app.models.event import Event
    from app.models.file import File


class ReviewStatus:
    """Shared review state strings (plain constants, stored as text)."""

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class Evidence(Base, UUIDPk, TimestampMixin):
    __tablename__ = "evidence"
    __table_args__ = (
        Index("ix_evidence_case_id_evidence_number", "case_id", "evidence_number"),
        UniqueConstraint("case_id", "evidence_number", name="uq_evidence_case_number"),
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_file_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("files.id", ondelete="SET NULL"), nullable=True
    )
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("document_analyses.id", ondelete="SET NULL"),
        nullable=True,
    )
    evidence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="other")
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    proof_purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=ReviewStatus.PENDING, server_default="PENDING"
    )
    # Field names a human has edited. Once a field is listed here a later
    # re-analysis must never overwrite it (docs/14 "用户修改优先").
    user_edited_fields: Mapped[list | None] = mapped_column(JSON, nullable=True)

    case: Mapped["Case"] = relationship(back_populates="evidence")
    source_file: Mapped["File | None"] = relationship(back_populates="evidence")
    events: Mapped[list["Event"]] = relationship(
        secondary="evidence_events", back_populates="evidence", lazy="selectin"
    )
    persons: Mapped[list["Person"]] = relationship(
        secondary="evidence_persons", back_populates="evidence", lazy="selectin"
    )
    claims: Mapped[list["Claim"]] = relationship(
        secondary="evidence_claims", back_populates="evidence", lazy="selectin"
    )

    @property
    def edited_fields(self) -> list[str]:
        return list(self.user_edited_fields or [])

    def mark_edited(self, field_name: str) -> None:
        current = list(self.user_edited_fields or [])
        if field_name not in current:
            current.append(field_name)
            self.user_edited_fields = current


class Person(Base, UUIDPk, TimestampMixin):
    __tablename__ = "persons"

    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    organization: Mapped[str | None] = mapped_column(String(200), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    evidence: Mapped[list["Evidence"]] = relationship(
        secondary="evidence_persons", back_populates="persons", lazy="selectin"
    )


class EvidenceEvent(Base):
    """evidence ↔ event join (docs/05_DATABASE_SCHEMA.md)."""

    __tablename__ = "evidence_events"

    evidence_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("evidence.id", ondelete="CASCADE"), primary_key=True
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )


class EvidencePerson(Base):
    __tablename__ = "evidence_persons"

    evidence_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("evidence.id", ondelete="CASCADE"), primary_key=True
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), primary_key=True
    )


class EvidenceClaim(Base):
    __tablename__ = "evidence_claims"

    evidence_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("evidence.id", ondelete="CASCADE"), primary_key=True
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), primary_key=True
    )
