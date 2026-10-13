"""MaterialPackage models — arbitration evidence package (Phase 9-A).

A package only *arranges* existing evidence: it never owns or mutates the
original files/evidence rows. Snapshots are append-only; there is no code
path that updates an existing snapshot row (same immutability convention as
`CaseEvidenceGapResult`).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, UUID as PGUUID

from app.db import Base
from app.models.base import TimestampMixin, UUIDPk

if TYPE_CHECKING:
    from app.models.case import Case
    from app.models.evidence import Evidence


class PackageStatus:
    """Package lifecycle states (plain constants, stored as text)."""

    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class ItemReviewStatus:
    """Per-item review state inside a package."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class MaterialPackage(Base, UUIDPk, TimestampMixin):
    """One arbitration material package bound to a case."""

    __tablename__ = "material_packages"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')",
            name="ck_material_package_status",
        ),
        CheckConstraint("draft_version > 0", name="ck_material_package_version_positive"),
        Index("ix_material_packages_case_id_created_at", "case_id", "created_at"),
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=PackageStatus.DRAFT,
        server_default=PackageStatus.DRAFT,
    )
    # Optimistic-lock counter: every successful draft item save bumps it;
    # clients must echo the value they loaded (docs/12 concurrency rule).
    draft_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    case: Mapped["Case"] = relationship(back_populates="material_packages")
    items: Mapped[list["MaterialPackageItem"]] = relationship(
        back_populates="package",
        cascade="all, delete-orphan",
        order_by="MaterialPackageItem.item_order",
        lazy="selectin",
    )
    snapshots: Mapped[list["MaterialPackageSnapshot"]] = relationship(
        back_populates="package",
        cascade="all, delete-orphan",
        order_by="MaterialPackageSnapshot.version",
        lazy="selectin",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<MaterialPackage {self.name!r} {self.status}>"


class MaterialPackageItem(Base, UUIDPk, TimestampMixin):
    """One evidence entry inside a package draft.

    The ordering/numbering constraints are DEFERRABLE so a batch reorder
    (swap positions 1 and 2) can be applied atomically inside one
    transaction; PostgreSQL checks them at COMMIT instead of per statement.
    """

    __tablename__ = "material_package_items"
    __table_args__ = (
        UniqueConstraint(
            "package_id",
            "evidence_id",
            name="uq_material_package_item_evidence",
        ),
        UniqueConstraint(
            "package_id",
            "item_order",
            name="uq_material_package_item_order",
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint(
            "package_id",
            "display_number",
            name="uq_material_package_item_display_number",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("item_order > 0", name="ck_material_package_item_order_positive"),
        CheckConstraint("display_number >= 1", name="ck_material_package_item_number_positive"),
        CheckConstraint(
            "review_status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_material_package_item_review_status",
        ),
        Index("ix_material_package_items_package_id", "package_id"),
    )

    package_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("material_packages.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("evidence.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_order: Mapped[int] = mapped_column(Integer, nullable=False)
    display_number: Mapped[int] = mapped_column(Integer, nullable=False)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    proof_purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=ItemReviewStatus.PENDING,
        server_default=ItemReviewStatus.PENDING,
    )

    package: Mapped["MaterialPackage"] = relationship(back_populates="items")
    evidence: Mapped["Evidence"] = relationship(lazy="joined")


class MaterialPackageSnapshot(Base, UUIDPk, TimestampMixin):
    """Immutable point-in-time copy of a package draft.

    Rows are only ever inserted. `content` stores the complete serialized
    state (package metadata + every item with order, numbers, display info
    and the source evidence version captured at creation time), so the
    snapshot stays readable even after the draft or the evidence changes.
    """

    __tablename__ = "material_package_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "package_id", "version", name="uq_material_package_snapshot_version"
        ),
        CheckConstraint("version > 0", name="ck_material_package_snapshot_version_positive"),
        Index("ix_material_package_snapshots_package_id", "package_id"),
        Index("ix_material_package_snapshots_package_id_created_at", "package_id", "created_at"),
    )

    package_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("material_packages.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # The package.draft_version at capture time: lets readers detect whether
    # the draft moved on after this snapshot was taken.
    draft_version_captured: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    package: Mapped["MaterialPackage"] = relationship(back_populates="snapshots")
