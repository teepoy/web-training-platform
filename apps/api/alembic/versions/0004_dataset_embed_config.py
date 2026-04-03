"""Add embed_config column to datasets table

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-03 00:00:00.000000+00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "datasets",
        sa.Column("embed_config", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("datasets", "embed_config")
