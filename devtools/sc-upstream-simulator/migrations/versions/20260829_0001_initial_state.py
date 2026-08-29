"""Create simulator-owned inspection publication state.

Revision ID: 20260829_0001
Revises:
Create Date: 2026-08-29
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260829_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "simulator_clock",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("next_change_token", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_simulator_clock_singleton"),
        sa.CheckConstraint(
            "next_change_token > 0", name="ck_simulator_clock_positive_token"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(
        sa.table(
            "simulator_clock",
            sa.column("id", sa.SmallInteger()),
            sa.column("next_change_token", sa.BigInteger()),
        ),
        [{"id": 1, "next_change_token": 1}],
    )

    op.create_table(
        "simulator_inspections",
        sa.Column("wafer_key", sa.BigInteger(), nullable=False),
        sa.Column("inspection_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lot_id", sa.String(length=50), nullable=False),
        sa.Column("wafer_id", sa.String(length=50), nullable=False),
        sa.Column("layer_id", sa.String(length=50), nullable=False),
        sa.Column("device", sa.String(length=50), nullable=False),
        sa.Column("inspect_equip_id", sa.String(length=50), nullable=False),
        sa.Column("recipe_key", sa.BigInteger(), nullable=False),
        sa.Column("recipe_id", sa.String(length=50), nullable=False),
        sa.Column("origin_index_x", sa.Integer(), nullable=False),
        sa.Column("origin_index_y", sa.Integer(), nullable=False),
        sa.Column("center_x", sa.Integer(), nullable=False),
        sa.Column("center_y", sa.Integer(), nullable=False),
        sa.Column("origin_x", sa.Integer(), nullable=False),
        sa.Column("origin_y", sa.Integer(), nullable=False),
        sa.Column("die_size_x", sa.Integer(), nullable=False),
        sa.Column("die_size_y", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("change_token", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "state IN ('draft', 'published')", name="ck_simulator_inspection_state"
        ),
        sa.CheckConstraint(
            "(state = 'draft' AND published_at IS NULL AND last_updated_at IS NULL "
            "AND change_token IS NULL) OR "
            "(state = 'published' AND published_at IS NOT NULL "
            "AND last_updated_at IS NOT NULL AND change_token IS NOT NULL)",
            name="ck_simulator_inspection_publication_fields",
        ),
        sa.PrimaryKeyConstraint("wafer_key", "inspection_time"),
        sa.UniqueConstraint(
            "change_token", name="uq_simulator_inspection_change_token"
        ),
    )
    op.create_index(
        "ix_simulator_inspections_published_time",
        "simulator_inspections",
        ["state", "inspection_time"],
        unique=False,
    )

    op.create_table(
        "simulator_defects",
        sa.Column("wafer_key", sa.BigInteger(), nullable=False),
        sa.Column("inspection_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("defect_id", sa.BigInteger(), nullable=False),
        sa.Column("test_id", sa.Integer(), nullable=False),
        sa.Column("class_number", sa.Integer(), nullable=False),
        sa.Column("rough_bin", sa.Integer(), nullable=False),
        sa.Column("wafer_x", sa.Integer(), nullable=False),
        sa.Column("wafer_y", sa.Integer(), nullable=False),
        sa.Column("index_x", sa.Integer(), nullable=False),
        sa.Column("index_y", sa.Integer(), nullable=False),
        sa.Column("adder", sa.Integer(), nullable=False),
        sa.Column("cluster", sa.Integer(), nullable=False),
        sa.Column("images", sa.Integer(), nullable=False),
        sa.Column("size_x", sa.Integer(), nullable=False),
        sa.Column("size_y", sa.Integer(), nullable=False),
        sa.Column("size_d", sa.Integer(), nullable=False),
        sa.Column("area", sa.Integer(), nullable=False),
        sa.Column("final_bin", sa.Integer(), nullable=False),
        sa.Column("manual_bin", sa.Integer(), nullable=False),
        sa.Column("kill_ratio", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["wafer_key", "inspection_time"],
            [
                "simulator_inspections.wafer_key",
                "simulator_inspections.inspection_time",
            ],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("wafer_key", "inspection_time", "defect_id"),
    )

    op.create_table(
        "simulator_review_images",
        sa.Column("wafer_key", sa.BigInteger(), nullable=False),
        sa.Column("inspection_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("defect_id", sa.BigInteger(), nullable=False),
        sa.Column("image_id", sa.BigInteger(), nullable=False),
        sa.Column("image_type", sa.String(length=50), nullable=False),
        sa.Column("image_filespec", sa.String(length=1024), nullable=False),
        sa.ForeignKeyConstraint(
            ["wafer_key", "inspection_time"],
            [
                "simulator_inspections.wafer_key",
                "simulator_inspections.inspection_time",
            ],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "wafer_key", "inspection_time", "defect_id", "image_id"
        ),
    )

    op.create_table(
        "simulator_patch_archives",
        sa.Column("wafer_key", sa.BigInteger(), nullable=False),
        sa.Column("inspection_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archive_id", sa.BigInteger(), nullable=False),
        sa.Column("s3_bucket", sa.String(length=255), nullable=False),
        sa.Column("s3_key", sa.String(length=512), nullable=False),
        sa.ForeignKeyConstraint(
            ["wafer_key", "inspection_time"],
            [
                "simulator_inspections.wafer_key",
                "simulator_inspections.inspection_time",
            ],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("wafer_key", "inspection_time", "archive_id"),
        sa.UniqueConstraint(
            "wafer_key",
            "inspection_time",
            "s3_bucket",
            "s3_key",
            name="uq_simulator_patch_archive_object",
        ),
    )


def downgrade() -> None:
    op.drop_table("simulator_patch_archives")
    op.drop_table("simulator_review_images")
    op.drop_table("simulator_defects")
    op.drop_index(
        "ix_simulator_inspections_published_time",
        table_name="simulator_inspections",
    )
    op.drop_table("simulator_inspections")
    op.drop_table("simulator_clock")
