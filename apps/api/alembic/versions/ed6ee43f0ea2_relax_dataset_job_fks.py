"""relax_dataset_job_fks

Revision ID: ed6ee43f0ea2
Revises: 3a6f6cc3f1c2
Create Date: 2026-06-26 08:02:11.108160

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "ed6ee43f0ea2"
down_revision = "3a6f6cc3f1c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("artifacts_job_id_fkey", "artifacts", type_="foreignkey")
    op.create_foreign_key(
        "artifacts_job_id_fkey",
        "artifacts",
        "training_jobs",
        ["job_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column("artifacts", "job_id", existing_type=sa.String(64), nullable=True)

    op.drop_constraint(
        "training_jobs_dataset_id_fkey", "training_jobs", type_="foreignkey"
    )
    op.create_foreign_key(
        "training_jobs_dataset_id_fkey",
        "training_jobs",
        "datasets",
        ["dataset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column(
        "training_jobs", "dataset_id", existing_type=sa.String(64), nullable=True
    )

    op.drop_constraint(
        "prediction_jobs_dataset_id_fkey", "prediction_jobs", type_="foreignkey"
    )
    op.create_foreign_key(
        "prediction_jobs_dataset_id_fkey",
        "prediction_jobs",
        "datasets",
        ["dataset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column(
        "prediction_jobs", "dataset_id", existing_type=sa.String(64), nullable=True
    )


def downgrade() -> None:
    op.alter_column(
        "prediction_jobs", "dataset_id", existing_type=sa.String(64), nullable=False
    )
    op.drop_constraint(
        "prediction_jobs_dataset_id_fkey", "prediction_jobs", type_="foreignkey"
    )
    op.create_foreign_key(
        "prediction_jobs_dataset_id_fkey",
        "prediction_jobs",
        "datasets",
        ["dataset_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.alter_column(
        "training_jobs", "dataset_id", existing_type=sa.String(64), nullable=False
    )
    op.drop_constraint(
        "training_jobs_dataset_id_fkey", "training_jobs", type_="foreignkey"
    )
    op.create_foreign_key(
        "training_jobs_dataset_id_fkey",
        "training_jobs",
        "datasets",
        ["dataset_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.alter_column("artifacts", "job_id", existing_type=sa.String(64), nullable=False)
    op.drop_constraint("artifacts_job_id_fkey", "artifacts", type_="foreignkey")
    op.create_foreign_key(
        "artifacts_job_id_fkey",
        "artifacts",
        "training_jobs",
        ["job_id"],
        ["id"],
        ondelete="CASCADE",
    )
