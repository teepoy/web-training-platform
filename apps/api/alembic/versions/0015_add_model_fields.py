"""add model fields to artifacts

Revision ID: 0015_add_model_fields
Revises: a1b2c3d4e5f6
Create Date: 2026-04-07
"""

from alembic import op
import sqlalchemy as sa


revision = "0015_add_model_fields"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add model-specific optional fields to artifacts table
    op.add_column("artifacts", sa.Column("name", sa.String(length=255), nullable=True))
    op.add_column("artifacts", sa.Column("file_size", sa.BigInteger(), nullable=True))
    op.add_column("artifacts", sa.Column("file_hash", sa.String(length=64), nullable=True))
    op.add_column("artifacts", sa.Column("format", sa.String(length=64), nullable=True))
    op.add_column("artifacts", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    
    # Add index for querying models by kind
    op.create_index("ix_artifacts_kind", "artifacts", ["kind"])
    op.create_index("ix_artifacts_job_id", "artifacts", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_artifacts_job_id", table_name="artifacts")
    op.drop_index("ix_artifacts_kind", table_name="artifacts")
    op.drop_column("artifacts", "created_at")
    op.drop_column("artifacts", "format")
    op.drop_column("artifacts", "file_hash")
    op.drop_column("artifacts", "file_size")
    op.drop_column("artifacts", "name")
