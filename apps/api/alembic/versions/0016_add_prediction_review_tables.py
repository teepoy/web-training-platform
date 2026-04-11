"""add prediction review actions and annotation versions tables

Revision ID: 0016_add_prediction_review_tables
Revises: 0015_add_model_fields
Create Date: 2026-04-10
"""

from alembic import op
import sqlalchemy as sa


revision = "0016_add_prediction_review_tables"
down_revision = "0015_add_model_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prediction_review_actions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("dataset_id", sa.String(64), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_id", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(255), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_prediction_review_actions_dataset_id", "prediction_review_actions", ["dataset_id"])

    op.create_table(
        "annotation_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("review_action_id", sa.String(64), sa.ForeignKey("prediction_review_actions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("annotation_id", sa.String(64), sa.ForeignKey("annotations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_prediction_id", sa.Integer(), nullable=True),
        sa.Column("predicted_label", sa.String(255), nullable=False),
        sa.Column("final_label", sa.String(255), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_annotation_versions_review_action_id", "annotation_versions", ["review_action_id"])
    op.create_index("ix_annotation_versions_annotation_id", "annotation_versions", ["annotation_id"])


def downgrade() -> None:
    op.drop_index("ix_annotation_versions_annotation_id", table_name="annotation_versions")
    op.drop_index("ix_annotation_versions_review_action_id", table_name="annotation_versions")
    op.drop_table("annotation_versions")
    op.drop_index("ix_prediction_review_actions_dataset_id", table_name="prediction_review_actions")
    op.drop_table("prediction_review_actions")
