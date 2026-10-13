"""add_case_evidence_gap_results

Revision ID: 443a6f78858c
Revises: 1e0da99c76db
Create Date: 2026-10-11 05:10:50.393263
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op



revision: str = '443a6f78858c'
down_revision: str | None = '1e0da99c76db'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'case_evidence_gap_results',
        sa.Column('case_id', sa.UUID(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('gap_json', sa.JSON(), nullable=True),
        sa.Column('error_type', sa.String(length=64), nullable=True),
        sa.Column('error_message', sa.String(length=1024), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('case_id', 'version', name='uq_gap_case_version'),
        sa.CheckConstraint('version > 0', name='ck_gap_version_positive'),
    )
    op.create_index('ix_gap_case_id_created_at', 'case_evidence_gap_results', ['case_id', 'created_at'], unique=False)
    # ix_case_evidence_gap_results_case_id is created by the follow-up
    # revision 45c25bf47d58 (fix_gap_index); creating it here as well made
    # `alembic upgrade head` fail on a fresh database with DuplicateTable.


def downgrade() -> None:
    # ix_case_evidence_gap_results_case_id is dropped by 45c25bf47d58's
    # downgrade (it is the revision that creates it).
    op.drop_index('ix_gap_case_id_created_at', table_name='case_evidence_gap_results')
    op.drop_table('case_evidence_gap_results')
