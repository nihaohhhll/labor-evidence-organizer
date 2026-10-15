"""Shared model mixins and helper columns."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UUID as PGUUID


def utcnow() -> datetime:
    """Timezone-aware UTC now(). Used for every timestamp in the system."""
    return datetime.now(timezone.utc)


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class UUIDPk:
    """UUID primary key, generated in Python so it is available before flush."""

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid
    )


class TimestampMixin:
    """created_at / updated_at maintained by SQLAlchemy.

    Defaults are Python-side (utcnow) so every insert/update carries
    microsecond-precision UTC even on SQLite, where the SQL fallback
    CURRENT_TIMESTAMP only has second precision — snapshot change detection
    (material_packages) compares updated_at values taken within the same
    second. func.now() stays as server_default for raw-SQL inserts.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=func.now(),
        onupdate=utcnow,
    )


class SoftDeleteMixin:
    """Soft delete: rows are never physically removed by the application."""

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


def varchar(length: int = 255) -> String:
    return String(length)
