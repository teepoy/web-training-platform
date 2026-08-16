"""add dataset revision audit history

Revision ID: e8f1a2b3c4d5
Revises: d4e5f6a7b8c9
Create Date: 2026-08-15 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "e8f1a2b3c4d5"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dataset_revisions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("manifest_uri", sa.Text(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("operation_ref", sa.String(length=255), nullable=True),
        sa.Column(
            "is_reproducible",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "revision_number > 0",
            name="ck_dataset_revisions_number_positive",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_id",
            "revision_number",
            name="uq_dataset_revisions_number",
        ),
    )
    op.create_index(
        "ix_dataset_revisions_dataset_id",
        "dataset_revisions",
        ["dataset_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_dataset_revisions_dataset_id", table_name="dataset_revisions")
    op.drop_table("dataset_revisions")
