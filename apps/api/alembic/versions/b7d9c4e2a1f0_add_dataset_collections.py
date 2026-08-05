"""add dataset collections

Revision ID: b7d9c4e2a1f0
Revises: ed6ee43f0ea2
Create Date: 2026-08-05 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "b7d9c4e2a1f0"
down_revision = "ed6ee43f0ea2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dataset_collections",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("target_view_id", sa.String(length=128), nullable=False),
        sa.Column("target_view_contract", sa.String(length=255), nullable=False),
        sa.Column("target_schema_version", sa.String(length=64), nullable=False),
        sa.Column("duplicate_policy", sa.String(length=64), nullable=False),
        sa.Column("missing_data_policy", sa.String(length=64), nullable=False),
        sa.Column(
            "definition_version", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "definition_version >= 0",
            name="ck_dataset_collections_definition_version_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "dataset_collection_members",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("collection_id", sa.String(length=64), nullable=False),
        sa.Column("source_dataset_id", sa.String(length=64), nullable=True),
        sa.Column("source_dataset_ref", sa.String(length=64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("linked_definition_version", sa.Integer(), nullable=False),
        sa.Column("unlinked_definition_version", sa.Integer(), nullable=True),
        sa.Column("filter_spec", sa.JSON(), nullable=False),
        sa.Column("label_mapping", sa.JSON(), nullable=False),
        sa.Column("sampling_spec", sa.JSON(), nullable=False),
        sa.Column("linked_by", sa.String(length=255), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("unlinked_by", sa.String(length=255), nullable=True),
        sa.Column("unlinked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "position >= 0",
            name="ck_dataset_collection_members_position_nonnegative",
        ),
        sa.CheckConstraint(
            "linked_definition_version > 0",
            name="ck_dataset_collection_members_linked_version_positive",
        ),
        sa.CheckConstraint(
            "unlinked_definition_version IS NULL OR "
            "unlinked_definition_version > linked_definition_version",
            name="ck_dataset_collection_members_version_interval",
        ),
        sa.CheckConstraint(
            "unlinked_at IS NOT NULL OR source_dataset_id IS NOT NULL",
            name="ck_dataset_collection_members_active_source_present",
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["dataset_collections.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_dataset_id"], ["datasets.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_dataset_collection_members_collection_id",
        "dataset_collection_members",
        ["collection_id"],
    )
    op.create_index(
        "ix_dataset_collection_members_source_dataset_id",
        "dataset_collection_members",
        ["source_dataset_id"],
    )
    op.create_index(
        "uq_dataset_collection_members_active_dataset",
        "dataset_collection_members",
        ["collection_id", "source_dataset_id"],
        unique=True,
        sqlite_where=sa.text("unlinked_at IS NULL"),
        postgresql_where=sa.text("unlinked_at IS NULL"),
    )
    op.create_table(
        "dataset_collection_revisions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("collection_id", sa.String(length=64), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("definition_version", sa.Integer(), nullable=False),
        sa.Column("definition_hash", sa.String(length=64), nullable=False),
        sa.Column("target_view_id", sa.String(length=128), nullable=False),
        sa.Column("target_view_contract", sa.String(length=255), nullable=False),
        sa.Column("target_schema_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("label_counts", sa.JSON(), nullable=False),
        sa.Column("manifest_uri", sa.Text(), nullable=True),
        sa.Column("provenance_uri", sa.Text(), nullable=True),
        sa.Column("trigger_kind", sa.String(length=64), nullable=False),
        sa.Column("trigger_ref", sa.String(length=255), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "revision_number > 0",
            name="ck_dataset_collection_revisions_number_positive",
        ),
        sa.CheckConstraint(
            "definition_version > 0",
            name="ck_dataset_collection_revisions_definition_version_positive",
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["dataset_collections.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "collection_id",
            "revision_number",
            name="uq_dataset_collection_revisions_number",
        ),
    )
    op.create_index(
        "ix_dataset_collection_revisions_collection_id",
        "dataset_collection_revisions",
        ["collection_id"],
    )
    op.add_column(
        "training_jobs", sa.Column("collection_id", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "training_jobs",
        sa.Column("collection_revision_id", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_training_jobs_collection_id",
        "training_jobs",
        "dataset_collections",
        ["collection_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_training_jobs_collection_revision_id",
        "training_jobs",
        "dataset_collection_revisions",
        ["collection_revision_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_training_jobs_collection_id", "training_jobs", ["collection_id"]
    )
    op.create_index(
        "ix_training_jobs_collection_revision_id",
        "training_jobs",
        ["collection_revision_id"],
    )
    op.add_column(
        "prediction_jobs",
        sa.Column("dataset_collection_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "prediction_jobs",
        sa.Column("dataset_collection_revision_id", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_prediction_jobs_dataset_collection_id",
        "prediction_jobs",
        "dataset_collections",
        ["dataset_collection_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_prediction_jobs_dataset_collection_revision_id",
        "prediction_jobs",
        "dataset_collection_revisions",
        ["dataset_collection_revision_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_prediction_jobs_dataset_collection_id",
        "prediction_jobs",
        ["dataset_collection_id"],
    )
    op.create_index(
        "ix_prediction_jobs_dataset_collection_revision_id",
        "prediction_jobs",
        ["dataset_collection_revision_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_prediction_jobs_dataset_collection_revision_id",
        table_name="prediction_jobs",
    )
    op.drop_index(
        "ix_prediction_jobs_dataset_collection_id", table_name="prediction_jobs"
    )
    op.drop_constraint(
        "fk_prediction_jobs_dataset_collection_revision_id",
        "prediction_jobs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_prediction_jobs_dataset_collection_id",
        "prediction_jobs",
        type_="foreignkey",
    )
    op.drop_column("prediction_jobs", "dataset_collection_revision_id")
    op.drop_column("prediction_jobs", "dataset_collection_id")
    op.drop_index(
        "ix_training_jobs_collection_revision_id", table_name="training_jobs"
    )
    op.drop_index("ix_training_jobs_collection_id", table_name="training_jobs")
    op.drop_constraint(
        "fk_training_jobs_collection_revision_id",
        "training_jobs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_training_jobs_collection_id", "training_jobs", type_="foreignkey"
    )
    op.drop_column("training_jobs", "collection_revision_id")
    op.drop_column("training_jobs", "collection_id")
    op.drop_index(
        "ix_dataset_collection_revisions_collection_id",
        table_name="dataset_collection_revisions",
    )
    op.drop_table("dataset_collection_revisions")
    op.drop_index(
        "uq_dataset_collection_members_active_dataset",
        table_name="dataset_collection_members",
    )
    op.drop_index(
        "ix_dataset_collection_members_source_dataset_id",
        table_name="dataset_collection_members",
    )
    op.drop_index(
        "ix_dataset_collection_members_collection_id",
        table_name="dataset_collection_members",
    )
    op.drop_table("dataset_collection_members")
    op.drop_table("dataset_collections")
