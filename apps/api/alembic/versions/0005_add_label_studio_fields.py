"""Add Label Studio linkage fields

Revision ID: 1a2b3c4d5e6f
Revises: 0004
Create Date: 2026-04-04 00:00:00.000000+00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "1a2b3c4d5e6f"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("datasets", sa.Column("ls_project_id", sa.String(length=255), nullable=True))
    op.add_column("samples", sa.Column("ls_task_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("samples", "ls_task_id")
    op.drop_column("datasets", "ls_project_id")
