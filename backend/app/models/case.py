"""Case model — the top level container for one dispute's materials."""

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, UUID as PGUUID

from app.db import Base
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDPk

if TYPE_CHECKING:
    from app.models.case_gap import CaseEvidenceGapResult
    from app.models.evidence import Evidence
    from app.models.event import Event
    from app.models.file import File
    from app.models.material_package import MaterialPackage
    from app.models.user import User


class CaseStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    CLOSED = "CLOSED"


class Case(Base, UUIDPk, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "cases"
    __table_args__ = (Index("ix_cases_user_id_deleted_at", "user_id", "deleted_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=CaseStatus.ACTIVE.value,
        server_default=CaseStatus.ACTIVE.value,
    )
    # 庭审准备 (workbench): hearing date/notice + user checklist overrides +
    # mediation/ruling notes. JSON keeps this 1:1 data off a new table.
    trial_prep: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    owner: Mapped["User"] = relationship(back_populates="cases")
    files: Mapped[list["File"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", lazy="selectin"
    )
    evidence: Mapped[list["Evidence"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", lazy="selectin"
    )
    events: Mapped[list["Event"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", lazy="selectin"
    )
    gap_results: Mapped[list["CaseEvidenceGapResult"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", lazy="selectin"
    )
    # Phase 9-A: packages arrange existing evidence; cascade mirrors A3.
    material_packages: Mapped[list["MaterialPackage"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Case {self.name!r}>"
