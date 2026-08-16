"""identify composite collection revision manifests

Revision ID: f9a2b3c4d5e6
Revises: e8f1a2b3c4d5
Create Date: 2026-08-15 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "f9a2b3c4d5e6"
down_revision = "e8f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dataset_collection_revisions",
        sa.Column(
            "manifest_format",
            sa.String(length=64),
            server_default="legacy_materialized_v1",
            nullable=False,
        ),
    )
    op.add_column(
        "dataset_collection_revisions",
        sa.Column(
            "source_resolution",
            sa.String(length=32),
            server_default="legacy_materialized",
            nullable=False,
        ),
    )
    op.add_column(
        "dataset_collection_revisions",
        sa.Column(
            "reproducibility_capability",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("dataset_collection_revisions", "reproducibility_capability")
    op.drop_column("dataset_collection_revisions", "source_resolution")
    op.drop_column("dataset_collection_revisions", "manifest_format")
