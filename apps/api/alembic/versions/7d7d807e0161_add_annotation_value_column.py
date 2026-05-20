"""add annotation_value column

Revision ID: 7d7d807e0161
Revises: rev0018_platform_preds
Create Date: 2026-05-20
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '7d7d807e0161'
down_revision = 'rev0018_platform_preds'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('annotations', sa.Column('annotation_value', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('annotations', 'annotation_value')
