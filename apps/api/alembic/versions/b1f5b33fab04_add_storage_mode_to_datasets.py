"""add storage_mode to datasets

Revision ID: b1f5b33fab04
Revises: rev0018_platform_preds
Create Date: 2026-05-13 07:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1f5b33fab04'
down_revision = 'rev0018_platform_preds'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'datasets',
        sa.Column(
            'storage_mode',
            sa.String(length=64),
            server_default='db_full',
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column('datasets', 'storage_mode')
