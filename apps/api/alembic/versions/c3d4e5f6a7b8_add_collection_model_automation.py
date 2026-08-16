"""add collection model automation

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-15 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "dataset_collections",
        sa.Column("default_model_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "dataset_collections",
        sa.Column(
            "model_binding_version",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "fk_dataset_collections_default_model_id_artifacts",
        "dataset_collections",
        "artifacts",
        ["default_model_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_dataset_collections_default_model_id",
        "dataset_collections",
        ["default_model_id"],
    )

    op.create_table(
        "collection_prediction_batches",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("collection_id", sa.String(length=64), nullable=False),
        sa.Column("collection_revision_id", sa.String(length=64), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["dataset_collections.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["collection_revision_id"],
            ["dataset_collection_revisions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["model_id"], ["artifacts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "collection_id",
            "kind",
            "request_id",
            name="uq_collection_prediction_batches_request",
        ),
    )
    op.create_index(
        "ix_collection_prediction_batches_collection_id",
        "collection_prediction_batches",
        ["collection_id"],
    )
    op.create_index(
        "ix_collection_prediction_batches_collection_revision_id",
        "collection_prediction_batches",
        ["collection_revision_id"],
    )
    op.create_index(
        "ix_collection_prediction_batches_model_id",
        "collection_prediction_batches",
        ["model_id"],
    )

    op.create_table(
        "collection_prediction_batch_items",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("batch_id", sa.String(length=64), nullable=False),
        sa.Column("member_id", sa.String(length=64), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("dataset_revision_id", sa.String(length=64), nullable=False),
        sa.Column("prediction_job_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["batch_id"], ["collection_prediction_batches.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["member_id"], ["dataset_collection_members.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["dataset_revision_id"], ["dataset_revisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["prediction_job_id"], ["prediction_jobs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "batch_id",
            "dataset_id",
            name="uq_collection_prediction_batch_items_dataset",
        ),
    )
    for column in (
        "batch_id",
        "member_id",
        "dataset_id",
        "dataset_revision_id",
        "prediction_job_id",
    ):
        op.create_index(
            f"ix_collection_prediction_batch_items_{column}",
            "collection_prediction_batch_items",
            [column],
        )


def downgrade() -> None:
    op.drop_table("collection_prediction_batch_items")
    op.drop_table("collection_prediction_batches")
    op.drop_index(
        "ix_dataset_collections_default_model_id",
        table_name="dataset_collections",
    )
    op.drop_constraint(
        "fk_dataset_collections_default_model_id_artifacts",
        "dataset_collections",
        type_="foreignkey",
    )
    op.drop_column("dataset_collections", "model_binding_version")
    op.drop_column("dataset_collections", "default_model_id")
