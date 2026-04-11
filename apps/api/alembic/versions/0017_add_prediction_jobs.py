"""add prediction jobs

Revision ID: 0017_add_prediction_jobs
Revises: 0016_add_prediction_review_tables
Create Date: 2026-04-11
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0017_add_prediction_jobs"
down_revision = "0016_add_prediction_review_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prediction_jobs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("org_id", sa.String(length=64), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), sa.ForeignKey("datasets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=255), nullable=True),
        sa.Column("sample_ids", sa.JSON(), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("external_job_id", sa.String(length=128), nullable=True),
    )
    op.create_table(
        "prediction_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(length=64), sa.ForeignKey("prediction_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("level", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_prediction_events_job_id", "prediction_events", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_prediction_events_job_id", table_name="prediction_events")
    op.drop_table("prediction_events")
    op.drop_table("prediction_jobs")
