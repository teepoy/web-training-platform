"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-03-31
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("dataset_type", sa.String(length=64), nullable=False),
        sa.Column("task_spec", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "samples",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("dataset_id", sa.String(length=64), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("image_uri", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
    )
    op.create_table(
        "annotations",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("sample_id", sa.String(length=64), sa.ForeignKey("samples.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "training_presets",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("model_spec", sa.JSON(), nullable=False),
        sa.Column("omegaconf_yaml", sa.Text(), nullable=False),
        sa.Column("dataloader_ref", sa.String(length=255), nullable=False),
    )
    op.create_table(
        "training_jobs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("dataset_id", sa.String(length=64), sa.ForeignKey("datasets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("preset_id", sa.String(length=64), sa.ForeignKey("training_presets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("external_job_id", sa.String(length=128), nullable=True),
    )
    op.create_table(
        "training_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(length=64), sa.ForeignKey("training_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("level", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_training_events_job_id", "training_events", ["job_id"])
    op.create_table(
        "job_user_state",
        sa.Column("job_id", sa.String(length=64), sa.ForeignKey("training_jobs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_left", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("job_id", sa.String(length=64), sa.ForeignKey("training_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uri", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
    )
    op.create_table(
        "sample_features",
        sa.Column("sample_id", sa.String(length=64), sa.ForeignKey("samples.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("embedding", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sample_features")
    op.drop_table("artifacts")
    op.drop_table("job_user_state")
    op.drop_index("ix_training_events_job_id", table_name="training_events")
    op.drop_table("training_events")
    op.drop_table("training_jobs")
    op.drop_table("training_presets")
    op.drop_table("annotations")
    op.drop_table("samples")
    op.drop_table("datasets")
