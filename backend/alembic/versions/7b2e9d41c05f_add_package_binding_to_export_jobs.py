"""add package binding to export_jobs (Phase 9-C)

Revision ID: 7b2e9d41c05f
Revises: 9f3c2d7a1b58
Create Date: 2026-10-13 02:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '7b2e9d41c05f'
down_revision: str | None = '9f3c2d7a1b58'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'export_jobs',
        sa.Column('package_id', sa.UUID(), nullable=True),
    )
    op.add_column(
        'export_jobs',
        sa.Column('snapshot_id', sa.UUID(), nullable=True),
    )
    op.add_column(
        'export_jobs',
        sa.Column('snapshot_version', sa.Integer(), nullable=True),
    )
    op.add_column(
        'export_jobs',
        sa.Column('include_gap_appendix', sa.Boolean(), server_default='false', nullable=False),
    )
    op.add_column(
        'export_jobs',
        sa.Column('gap_result_id', sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        'fk_export_jobs_package_id',
        'export_jobs', 'material_packages',
        ['package_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_export_jobs_snapshot_id',
        'export_jobs', 'material_package_snapshots',
        ['snapshot_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_export_jobs_gap_result_id',
        'export_jobs', 'case_evidence_gap_results',
        ['gap_result_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_index(op.f('ix_export_jobs_package_id'), 'export_jobs', ['package_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_export_jobs_package_id'), table_name='export_jobs')
    op.drop_constraint('fk_export_jobs_gap_result_id', 'export_jobs', type_='foreignkey')
    op.drop_constraint('fk_export_jobs_snapshot_id', 'export_jobs', type_='foreignkey')
    op.drop_constraint('fk_export_jobs_package_id', 'export_jobs', type_='foreignkey')
    op.drop_column('export_jobs', 'gap_result_id')
    op.drop_column('export_jobs', 'include_gap_appendix')
    op.drop_column('export_jobs', 'snapshot_version')
    op.drop_column('export_jobs', 'snapshot_id')
    op.drop_column('export_jobs', 'package_id')
