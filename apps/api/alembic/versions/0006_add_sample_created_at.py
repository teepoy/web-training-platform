"""Add created_at column to samples table

Revision ID: 2b3c4d5e6f7a
Revises: 1a2b3c4d5e6f
Create Date: 2026-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "2b3c4d5e6f7a"
down_revision = "1a2b3c4d5e6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("samples") as batch_op:
        batch_op.add_column(
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("samples") as batch_op:
        batch_op.drop_column("created_at")
