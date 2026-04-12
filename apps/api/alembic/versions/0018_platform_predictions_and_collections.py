"""add platform predictions and collections

Revision ID: 0018_platform_predictions_and_collections
Revises: 0017_add_prediction_jobs
Create Date: 2026-04-12
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0018_platform_predictions_and_collections"
down_revision = "0017_add_prediction_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_predictions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("org_id", sa.String(length=64), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sample_id", sa.String(length=64), sa.ForeignKey("samples.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.String(length=64), sa.ForeignKey("prediction_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("model_version", sa.String(length=255), nullable=True),
        sa.Column("predicted_label", sa.String(length=255), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("all_scores_json", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_platform_predictions_org_id", "platform_predictions", ["org_id"])
    op.create_index("ix_platform_predictions_dataset_id", "platform_predictions", ["dataset_id"])
    op.create_index("ix_platform_predictions_sample_id", "platform_predictions", ["sample_id"])
    op.create_index("ix_platform_predictions_model_id", "platform_predictions", ["model_id"])
    op.create_index("ix_platform_predictions_job_id", "platform_predictions", ["job_id"])
    op.create_index("ix_platform_predictions_model_version", "platform_predictions", ["model_version"])
    op.create_index("ix_platform_predictions_created_at", "platform_predictions", ["created_at"])

    op.create_table(
        "prediction_collections",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("org_id", sa.String(length=64), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("model_version", sa.String(length=255), nullable=True),
        sa.Column("target", sa.String(length=64), nullable=False),
        sa.Column("source_job_id", sa.String(length=64), sa.ForeignKey("prediction_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sync_tag", sa.String(length=255), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_prediction_collections_org_id", "prediction_collections", ["org_id"])
    op.create_index("ix_prediction_collections_dataset_id", "prediction_collections", ["dataset_id"])
    op.create_index("ix_prediction_collections_model_id", "prediction_collections", ["model_id"])
    op.create_index("ix_prediction_collections_source_job_id", "prediction_collections", ["source_job_id"])

    op.create_table(
        "prediction_collection_items",
        sa.Column("collection_id", sa.String(length=64), sa.ForeignKey("prediction_collections.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("prediction_id", sa.String(length=64), sa.ForeignKey("platform_predictions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.add_column("prediction_review_actions", sa.Column("collection_id", sa.String(length=64), nullable=True))
    op.add_column("prediction_review_actions", sa.Column("sync_tag", sa.String(length=255), nullable=True))
    op.create_foreign_key(
        "fk_prediction_review_actions_collection_id",
        "prediction_review_actions",
        "prediction_collections",
        ["collection_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_prediction_review_actions_collection_id", "prediction_review_actions", ["collection_id"])

    with op.batch_alter_table("annotation_versions") as batch_op:
        batch_op.add_column(sa.Column("prediction_id", sa.String(length=64), nullable=True))
        batch_op.create_index("ix_annotation_versions_prediction_id", ["prediction_id"])
        batch_op.create_foreign_key(
            "fk_annotation_versions_prediction_id",
            "platform_predictions",
            ["prediction_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.drop_column("source_prediction_id")


def downgrade() -> None:
    with op.batch_alter_table("annotation_versions") as batch_op:
        batch_op.add_column(sa.Column("source_prediction_id", sa.Integer(), nullable=True))
        batch_op.drop_constraint("fk_annotation_versions_prediction_id", type_="foreignkey")
        batch_op.drop_index("ix_annotation_versions_prediction_id")
        batch_op.drop_column("prediction_id")

    op.drop_index("ix_prediction_review_actions_collection_id", table_name="prediction_review_actions")
    op.drop_constraint("fk_prediction_review_actions_collection_id", "prediction_review_actions", type_="foreignkey")
    op.drop_column("prediction_review_actions", "sync_tag")
    op.drop_column("prediction_review_actions", "collection_id")

    op.drop_table("prediction_collection_items")
    op.drop_index("ix_prediction_collections_source_job_id", table_name="prediction_collections")
    op.drop_index("ix_prediction_collections_model_id", table_name="prediction_collections")
    op.drop_index("ix_prediction_collections_dataset_id", table_name="prediction_collections")
    op.drop_index("ix_prediction_collections_org_id", table_name="prediction_collections")
    op.drop_table("prediction_collections")

    op.drop_index("ix_platform_predictions_created_at", table_name="platform_predictions")
    op.drop_index("ix_platform_predictions_model_version", table_name="platform_predictions")
    op.drop_index("ix_platform_predictions_job_id", table_name="platform_predictions")
    op.drop_index("ix_platform_predictions_model_id", table_name="platform_predictions")
    op.drop_index("ix_platform_predictions_sample_id", table_name="platform_predictions")
    op.drop_index("ix_platform_predictions_dataset_id", table_name="platform_predictions")
    op.drop_index("ix_platform_predictions_org_id", table_name="platform_predictions")
    op.drop_table("platform_predictions")
