"""Add exclusive SC automation partition assignments.

Revision ID: f1a2b3c4d5e6
Revises: e6f7a8b9c0d1
Create Date: 2026-08-29

Existing membership rules are intentionally not backfilled. Only explicitly
created SC automation partitions participate in the exclusivity constraint.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "e6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sc_automation_partitions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("collection_id", sa.String(length=64), nullable=False),
        sa.Column("rule_id", sa.String(length=64), nullable=False),
        sa.Column("connector_id", sa.String(length=64), nullable=False),
        sa.Column("layer_id", sa.String(length=255), nullable=False),
        sa.Column("dimension", sa.String(length=32), nullable=False),
        sa.Column("dimension_value", sa.String(length=255), nullable=False),
        sa.Column("partition_key", sa.String(length=640), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "dimension IN ('device', 'recipe_id')",
            name="ck_sc_automation_partition_dimension",
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["dataset_collections.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["connector_id"], ["source_connectors.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["collection_membership_rules.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_id", name="uq_sc_automation_partitions_rule"),
        sa.UniqueConstraint(
            "org_id",
            "connector_id",
            "partition_key",
            name="uq_sc_automation_partition_assignment",
        ),
    )
    op.create_index(
        "ix_sc_automation_partitions_org_id", "sc_automation_partitions", ["org_id"]
    )
    op.create_index(
        "ix_sc_automation_partitions_collection_id",
        "sc_automation_partitions",
        ["collection_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sc_automation_partitions_collection_id",
        table_name="sc_automation_partitions",
    )
    op.drop_index(
        "ix_sc_automation_partitions_org_id", table_name="sc_automation_partitions"
    )
    op.drop_table("sc_automation_partitions")
