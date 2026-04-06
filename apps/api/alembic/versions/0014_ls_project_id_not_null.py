"""Make ls_project_id NOT NULL on datasets

Revision ID: a1b2c3d4e5f6
Revises: f0a1b2c3d4e5
Create Date: 2026-04-06 00:00:00.000000+00:00

Alpha project — no production data, so we can safely alter the column.
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("datasets") as batch_op:
        batch_op.alter_column(
            "ls_project_id",
            existing_type=sa.String(255),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("datasets") as batch_op:
        batch_op.alter_column(
            "ls_project_id",
            existing_type=sa.String(255),
            nullable=True,
        )
