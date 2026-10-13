"""add_material_packages (Phase 9-A)

Revision ID: 9f3c2d7a1b58
Revises: 45c25bf47d58
Create Date: 2026-10-12 03:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op



revision: str = '9f3c2d7a1b58'
down_revision: str | None = '45c25bf47d58'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.create_table(
        'material_packages',
        sa.Column('case_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='DRAFT', nullable=False),
        sa.Column('draft_version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name='ck_material_package_status'),
        sa.CheckConstraint('draft_version > 0', name='ck_material_package_version_positive'),
    )
    op.create_index('ix_material_packages_case_id', 'material_packages', ['case_id'], unique=False)
    op.create_index('ix_material_packages_case_id_created_at', 'material_packages', ['case_id', 'created_at'], unique=False)

    op.create_table(
        'material_package_items',
        sa.Column('package_id', sa.UUID(), nullable=False),
        sa.Column('evidence_id', sa.UUID(), nullable=False),
        sa.Column('item_order', sa.Integer(), nullable=False),
        sa.Column('display_number', sa.Integer(), nullable=False),
        sa.Column('display_name', sa.String(length=300), nullable=False),
        sa.Column('proof_purpose', sa.Text(), nullable=True),
        sa.Column('review_status', sa.String(length=24), server_default='PENDING', nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['package_id'], ['material_packages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['evidence_id'], ['evidence.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('package_id', 'evidence_id', name='uq_material_package_item_evidence'),
        # DEFERRABLE so a batch reorder inside one transaction can swap
        # positions without tripping the constraint statement by statement.
        sa.UniqueConstraint('package_id', 'item_order', name='uq_material_package_item_order', deferrable=True, initially='DEFERRED'),
        sa.UniqueConstraint('package_id', 'display_number', name='uq_material_package_item_display_number', deferrable=True, initially='DEFERRED'),
        sa.CheckConstraint('item_order > 0', name='ck_material_package_item_order_positive'),
        sa.CheckConstraint('display_number >= 1', name='ck_material_package_item_number_positive'),
        sa.CheckConstraint("review_status IN ('PENDING', 'APPROVED', 'REJECTED')", name='ck_material_package_item_review_status'),
    )
    op.create_index('ix_material_package_items_package_id', 'material_package_items', ['package_id'], unique=False)

    op.create_table(
        'material_package_snapshots',
        sa.Column('package_id', sa.UUID(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('draft_version_captured', sa.Integer(), nullable=False),
        sa.Column('content', sa.JSON(), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['package_id'], ['material_packages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('package_id', 'version', name='uq_material_package_snapshot_version'),
        sa.CheckConstraint('version > 0', name='ck_material_package_snapshot_version_positive'),
    )
    op.create_index('ix_material_package_snapshots_package_id', 'material_package_snapshots', ['package_id'], unique=False)
    op.create_index('ix_material_package_snapshots_package_id_created_at', 'material_package_snapshots', ['package_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_material_package_snapshots_package_id_created_at', table_name='material_package_snapshots')
    op.drop_index('ix_material_package_snapshots_package_id', table_name='material_package_snapshots')
    op.drop_table('material_package_snapshots')
    op.drop_index('ix_material_package_items_package_id', table_name='material_package_items')
    op.drop_table('material_package_items')
    op.drop_index('ix_material_packages_case_id_created_at', table_name='material_packages')
    op.drop_index('ix_material_packages_case_id', table_name='material_packages')
    op.drop_table('material_packages')
