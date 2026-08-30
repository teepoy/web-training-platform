"""make Collection revisions identity-only and simplify SC partitions

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-08-30
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a2b3c4d5e6f7"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    incompatible_partitions = op.get_bind().execute(
        sa.text(
            "SELECT dimension, count(*) "
            "FROM sc_automation_partitions "
            "WHERE dimension != 'device' "
            "GROUP BY dimension ORDER BY dimension"
        )
    ).all()
    if incompatible_partitions:
        summary = ", ".join(
            f"{dimension} ({count})" for dimension, count in incompatible_partitions
        )
        raise RuntimeError(
            "Legacy sc_automation_partitions contain incompatible dimensions: "
            f"{summary}. Before retrying this migration, remove or reassign every "
            "non-device partition to an explicit layer_id + device partition."
        )

    with op.batch_alter_table("dataset_collection_revisions") as batch_op:
        batch_op.alter_column("source_snapshot", new_column_name="members")
        batch_op.drop_column("row_count")
        batch_op.drop_column("label_counts")
        batch_op.drop_column("provenance_uri")
        batch_op.drop_column("manifest_format")
        batch_op.drop_column("source_resolution")
        batch_op.drop_column("reproducibility_capability")

    with op.batch_alter_table("collection_discovery_runs") as batch_op:
        batch_op.alter_column(
            "snapshot_revision_id", new_column_name="collection_revision_id"
        )

    with op.batch_alter_table("source_import_profile_versions") as batch_op:
        batch_op.drop_constraint(
            "ck_source_import_profile_record_cap", type_="check"
        )
        batch_op.drop_constraint("ck_source_import_profile_row_cap", type_="check")
        batch_op.drop_column("max_records_per_run")
        batch_op.drop_column("max_rows_per_dataset")

    with op.batch_alter_table("sc_automation_partitions") as batch_op:
        batch_op.drop_constraint(
            "ck_sc_automation_partition_dimension", type_="check"
        )
        batch_op.alter_column("dimension_value", new_column_name="device")
        batch_op.drop_column("dimension")
    op.execute(
        "UPDATE sc_automation_partitions "
        "SET partition_key = json_build_array(layer_id, device)::text"
    )


def downgrade() -> None:
    with op.batch_alter_table("sc_automation_partitions") as batch_op:
        batch_op.add_column(sa.Column("dimension", sa.String(length=32)))
        batch_op.alter_column("device", new_column_name="dimension_value")
        batch_op.create_check_constraint(
            "ck_sc_automation_partition_dimension",
            "dimension IN ('device', 'recipe_id')",
        )
    op.execute("UPDATE sc_automation_partitions SET dimension = 'device'")
    op.execute(
        "UPDATE sc_automation_partitions "
        "SET partition_key = "
        "json_build_array(layer_id, 'device', dimension_value)::text"
    )
    with op.batch_alter_table("sc_automation_partitions") as batch_op:
        batch_op.alter_column("dimension", nullable=False)

    with op.batch_alter_table("source_import_profile_versions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "max_rows_per_dataset", sa.Integer(), nullable=False, server_default="1"
            )
        )
        batch_op.add_column(
            sa.Column(
                "max_records_per_run", sa.Integer(), nullable=False, server_default="1"
            )
        )
        batch_op.create_check_constraint(
            "ck_source_import_profile_row_cap", "max_rows_per_dataset > 0"
        )
        batch_op.create_check_constraint(
            "ck_source_import_profile_record_cap", "max_records_per_run > 0"
        )
        batch_op.alter_column("max_rows_per_dataset", server_default=None)
        batch_op.alter_column("max_records_per_run", server_default=None)

    with op.batch_alter_table("collection_discovery_runs") as batch_op:
        batch_op.alter_column(
            "collection_revision_id", new_column_name="snapshot_revision_id"
        )

    with op.batch_alter_table("dataset_collection_revisions") as batch_op:
        batch_op.add_column(sa.Column("row_count", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("label_counts", sa.JSON(), nullable=False, server_default="{}")
        )
        batch_op.add_column(sa.Column("provenance_uri", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "manifest_format",
                sa.String(length=64),
                nullable=False,
                server_default="collection-revision-membership.v1",
            )
        )
        batch_op.add_column(
            sa.Column(
                "source_resolution",
                sa.String(length=32),
                nullable=False,
                server_default="observed",
            )
        )
        batch_op.add_column(
            sa.Column(
                "reproducibility_capability",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.alter_column("members", new_column_name="source_snapshot")
        batch_op.alter_column("label_counts", server_default=None)
        batch_op.alter_column("manifest_format", server_default=None)
        batch_op.alter_column("source_resolution", server_default=None)
        batch_op.alter_column("reproducibility_capability", server_default=None)
