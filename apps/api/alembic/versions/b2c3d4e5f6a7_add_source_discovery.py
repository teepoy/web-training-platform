"""add typed source discovery and collection backfill persistence

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-15 00:00:00.000000

The migration creates only new control-plane records. Existing Dataset and
Collection rows are intentionally not backfilled or assigned source identity.
"""

from alembic import op
import sqlalchemy as sa


revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_connectors",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("provider_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "name", name="uq_source_connectors_org_name"),
    )
    op.create_index("ix_source_connectors_org_id", "source_connectors", ["org_id"])
    op.create_index(
        "ix_source_connectors_provider_id", "source_connectors", ["provider_id"]
    )

    op.create_table(
        "source_import_profile_versions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("profile_key", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("connector_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("max_records_per_run", sa.Integer(), nullable=False),
        sa.Column("max_rows_per_dataset", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_source_import_profile_version"),
        sa.CheckConstraint(
            "max_records_per_run > 0", name="ck_source_import_profile_record_cap"
        ),
        sa.CheckConstraint(
            "max_rows_per_dataset > 0", name="ck_source_import_profile_row_cap"
        ),
        sa.ForeignKeyConstraint(
            ["connector_id"], ["source_connectors.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "profile_key", "version", name="uq_source_import_profile_version"
        ),
    )
    op.create_index(
        "ix_source_import_profile_versions_connector_id",
        "source_import_profile_versions",
        ["connector_id"],
    )
    op.create_index(
        "ix_source_import_profile_versions_org_id",
        "source_import_profile_versions",
        ["org_id"],
    )
    op.create_index(
        "ix_source_import_profile_versions_profile_key",
        "source_import_profile_versions",
        ["profile_key"],
    )

    op.create_table(
        "collection_membership_rules",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("collection_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("active_version_id", sa.String(length=64), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("live_cursor", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["dataset_collections.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_collection_membership_rules_collection_id",
        "collection_membership_rules",
        ["collection_id"],
    )
    op.create_index(
        "ix_collection_membership_rules_org_id",
        "collection_membership_rules",
        ["org_id"],
    )

    op.create_table(
        "collection_membership_rule_versions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("rule_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("connector_id", sa.String(length=64), nullable=False),
        sa.Column("import_profile_version_id", sa.String(length=64), nullable=False),
        sa.Column("condition", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_collection_membership_rule_version"),
        sa.ForeignKeyConstraint(
            ["connector_id"], ["source_connectors.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["import_profile_version_id"],
            ["source_import_profile_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["collection_membership_rules.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "rule_id", "version", name="uq_collection_membership_rule_version"
        ),
    )
    op.create_index(
        "ix_collection_membership_rule_versions_rule_id",
        "collection_membership_rule_versions",
        ["rule_id"],
    )

    op.create_table(
        "collection_discovery_runs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("collection_id", sa.String(length=64), nullable=False),
        sa.Column("rule_id", sa.String(length=64), nullable=False),
        sa.Column("rule_version_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("as_of_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("range_start_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("range_end_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timezone_name", sa.String(length=128), nullable=True),
        sa.Column("parent_run_id", sa.String(length=64), nullable=True),
        sa.Column("snapshot_revision_id", sa.String(length=64), nullable=True),
        sa.Column("stats", sa.JSON(), nullable=False),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["dataset_collections.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["parent_run_id"], ["collection_discovery_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["collection_membership_rules.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["rule_version_id"],
            ["collection_membership_rule_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_revision_id"],
            ["dataset_collection_revisions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_collection_discovery_runs_collection_id",
        "collection_discovery_runs",
        ["collection_id"],
    )
    op.create_index(
        "ix_collection_discovery_runs_org_id", "collection_discovery_runs", ["org_id"]
    )
    op.create_index(
        "ix_collection_discovery_runs_rule_id",
        "collection_discovery_runs",
        ["rule_id"],
    )

    op.create_table(
        "collection_discovery_run_items",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("connector_id", sa.String(length=64), nullable=False),
        sa.Column("source_record_key", sa.String(length=512), nullable=False),
        sa.Column("source_version", sa.String(length=512), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), nullable=True),
        sa.Column("member_id", sa.String(length=64), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["connector_id"], ["source_connectors.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["member_id"], ["dataset_collection_members.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["collection_discovery_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id", "source_record_key", name="uq_discovery_run_source_record"
        ),
    )
    op.create_index(
        "ix_collection_discovery_run_items_run_id",
        "collection_discovery_run_items",
        ["run_id"],
    )

    op.create_table(
        "collection_import_receipts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("collection_id", sa.String(length=64), nullable=False),
        sa.Column("connector_id", sa.String(length=64), nullable=False),
        sa.Column("source_record_key", sa.String(length=512), nullable=False),
        sa.Column("source_version_key", sa.String(length=512), server_default="", nullable=False),
        sa.Column("import_profile_version_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempts > 0", name="ck_collection_import_attempts"),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["dataset_collections.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["connector_id"], ["source_connectors.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["import_profile_version_id"],
            ["source_import_profile_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "collection_id",
            "connector_id",
            "source_record_key",
            "source_version_key",
            "import_profile_version_id",
            name="uq_collection_import_identity",
        ),
    )
    op.create_index(
        "ix_collection_import_receipts_collection_id",
        "collection_import_receipts",
        ["collection_id"],
    )
    op.create_index(
        "ix_collection_import_receipts_org_id",
        "collection_import_receipts",
        ["org_id"],
    )

    op.create_table(
        "collection_discovery_receipts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("collection_id", sa.String(length=64), nullable=False),
        sa.Column("rule_id", sa.String(length=64), nullable=False),
        sa.Column("connector_id", sa.String(length=64), nullable=False),
        sa.Column("source_record_key", sa.String(length=512), nullable=False),
        sa.Column("source_version_key", sa.String(length=512), server_default="", nullable=False),
        sa.Column("import_profile_version_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), nullable=True),
        sa.Column("member_id", sa.String(length=64), nullable=True),
        sa.Column("first_run_id", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["dataset_collections.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["connector_id"], ["source_connectors.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["first_run_id"], ["collection_discovery_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["import_profile_version_id"],
            ["source_import_profile_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["member_id"], ["dataset_collection_members.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["collection_membership_rules.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "rule_id",
            "connector_id",
            "source_record_key",
            "source_version_key",
            "import_profile_version_id",
            name="uq_collection_discovery_receipt",
        ),
    )
    op.create_index(
        "ix_collection_discovery_receipts_collection_id",
        "collection_discovery_receipts",
        ["collection_id"],
    )

    op.create_table(
        "collection_source_memberships",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("collection_id", sa.String(length=64), nullable=False),
        sa.Column("connector_id", sa.String(length=64), nullable=False),
        sa.Column("source_record_key", sa.String(length=512), nullable=False),
        sa.Column("source_version", sa.String(length=512), nullable=True),
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("member_id", sa.String(length=64), nullable=False),
        sa.Column("admitted_by_rule_id", sa.String(length=64), nullable=False),
        sa.Column("admitted_by_run_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["admitted_by_rule_id"],
            ["collection_membership_rules.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["admitted_by_run_id"],
            ["collection_discovery_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["dataset_collections.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["connector_id"], ["source_connectors.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["member_id"], ["dataset_collection_members.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "collection_id",
            "connector_id",
            "source_record_key",
            name="uq_collection_source_membership",
        ),
    )
    op.create_index(
        "ix_collection_source_memberships_collection_id",
        "collection_source_memberships",
        ["collection_id"],
    )

    op.create_table(
        "collection_membership_suppressions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("collection_id", sa.String(length=64), nullable=False),
        sa.Column("connector_id", sa.String(length=64), nullable=False),
        sa.Column("source_record_key", sa.String(length=512), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cleared_by", sa.String(length=255), nullable=True),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["dataset_collections.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["connector_id"], ["source_connectors.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_collection_membership_suppressions_collection_id",
        "collection_membership_suppressions",
        ["collection_id"],
    )
    op.create_index(
        "uq_collection_active_suppression",
        "collection_membership_suppressions",
        ["collection_id", "connector_id", "source_record_key"],
        unique=True,
        sqlite_where=sa.text("cleared_at IS NULL"),
        postgresql_where=sa.text("cleared_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_collection_active_suppression",
        table_name="collection_membership_suppressions",
    )
    op.drop_index(
        "ix_collection_membership_suppressions_collection_id",
        table_name="collection_membership_suppressions",
    )
    op.drop_table("collection_membership_suppressions")
    op.drop_index(
        "ix_collection_source_memberships_collection_id",
        table_name="collection_source_memberships",
    )
    op.drop_table("collection_source_memberships")
    op.drop_index(
        "ix_collection_discovery_receipts_collection_id",
        table_name="collection_discovery_receipts",
    )
    op.drop_table("collection_discovery_receipts")
    op.drop_index(
        "ix_collection_import_receipts_org_id",
        table_name="collection_import_receipts",
    )
    op.drop_index(
        "ix_collection_import_receipts_collection_id",
        table_name="collection_import_receipts",
    )
    op.drop_table("collection_import_receipts")
    op.drop_index(
        "ix_collection_discovery_run_items_run_id",
        table_name="collection_discovery_run_items",
    )
    op.drop_table("collection_discovery_run_items")
    op.drop_index(
        "ix_collection_discovery_runs_rule_id",
        table_name="collection_discovery_runs",
    )
    op.drop_index(
        "ix_collection_discovery_runs_org_id",
        table_name="collection_discovery_runs",
    )
    op.drop_index(
        "ix_collection_discovery_runs_collection_id",
        table_name="collection_discovery_runs",
    )
    op.drop_table("collection_discovery_runs")
    op.drop_index(
        "ix_collection_membership_rule_versions_rule_id",
        table_name="collection_membership_rule_versions",
    )
    op.drop_table("collection_membership_rule_versions")
    op.drop_index(
        "ix_collection_membership_rules_org_id",
        table_name="collection_membership_rules",
    )
    op.drop_index(
        "ix_collection_membership_rules_collection_id",
        table_name="collection_membership_rules",
    )
    op.drop_table("collection_membership_rules")
    op.drop_index(
        "ix_source_import_profile_versions_profile_key",
        table_name="source_import_profile_versions",
    )
    op.drop_index(
        "ix_source_import_profile_versions_org_id",
        table_name="source_import_profile_versions",
    )
    op.drop_index(
        "ix_source_import_profile_versions_connector_id",
        table_name="source_import_profile_versions",
    )
    op.drop_table("source_import_profile_versions")
    op.drop_index("ix_source_connectors_provider_id", table_name="source_connectors")
    op.drop_index("ix_source_connectors_org_id", table_name="source_connectors")
    op.drop_table("source_connectors")
