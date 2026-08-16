"""record observed dataset revisions on training and prediction jobs

Revision ID: a1b2c3d4e5f6
Revises: f9a2b3c4d5e6
Create Date: 2026-08-15 00:00:00.000000

Historical jobs intentionally remain NULL. New Dataset-sourced submissions
record the current audit Revision before the job is persisted. This field is
provenance only and does not make runtime input reproducible.
"""

from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f6"
down_revision = "f9a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("training_jobs") as batch_op:
        batch_op.add_column(
            sa.Column("dataset_revision_id", sa.String(length=64), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_training_jobs_dataset_revision_id",
            "dataset_revisions",
            ["dataset_revision_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_training_jobs_dataset_revision_id",
            ["dataset_revision_id"],
        )

    with op.batch_alter_table("prediction_jobs") as batch_op:
        batch_op.add_column(
            sa.Column("dataset_revision_id", sa.String(length=64), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_prediction_jobs_dataset_revision_id",
            "dataset_revisions",
            ["dataset_revision_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_prediction_jobs_dataset_revision_id",
            ["dataset_revision_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("prediction_jobs") as batch_op:
        batch_op.drop_index("ix_prediction_jobs_dataset_revision_id")
        batch_op.drop_constraint(
            "fk_prediction_jobs_dataset_revision_id",
            type_="foreignkey",
        )
        batch_op.drop_column("dataset_revision_id")

    with op.batch_alter_table("training_jobs") as batch_op:
        batch_op.drop_index("ix_training_jobs_dataset_revision_id")
        batch_op.drop_constraint(
            "fk_training_jobs_dataset_revision_id",
            type_="foreignkey",
        )
        batch_op.drop_column("dataset_revision_id")
