"""claims extension + claim_events + cases.trial_prep (workbench phase).

Backwards compatible: every new column is nullable, the join table is new,
and the case JSON column defaults to NULL. Rollback drops exactly these
three objects with no data transformation.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c8f3a29d1b47"
down_revision: str | None = "7b2e9d41c05f"
branch_labels: str | list[str] | None = None
depends_on: str | list[str] | None = None


def upgrade() -> None:
    op.add_column("claims", sa.Column("amount", sa.String(length=64), nullable=True))
    op.add_column("claims", sa.Column("calculation", sa.Text(), nullable=True))
    op.add_column(
        "claims",
        sa.Column("status", sa.String(length=16), server_default="DRAFT", nullable=False),
    )
    op.add_column("claims", sa.Column("notes", sa.Text(), nullable=True))
    op.create_table(
        "claim_events",
        sa.Column("claim_id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("claim_id", "event_id"),
    )
    op.add_column("cases", sa.Column("trial_prep", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("cases", "trial_prep")
    op.drop_table("claim_events")
    op.drop_column("claims", "notes")
    op.drop_column("claims", "status")
    op.drop_column("claims", "calculation")
    op.drop_column("claims", "amount")
