"""Harden schedule persistence and expose cron timezone.

Revision ID: d4e5f6a7b8c9
Revises: b7d9c4e2a1f0
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "b7d9c4e2a1f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "schedules",
        sa.Column(
            "timezone",
            sa.String(length=128),
            nullable=False,
            server_default="UTC",
        ),
    )
    op.create_index(
        "ix_schedules_org_created_at",
        "schedules",
        ["org_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ux_schedules_prefect_deployment_id",
        "schedules",
        ["prefect_deployment_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_schedules_prefect_deployment_id", table_name="schedules")
    op.drop_index("ix_schedules_org_created_at", table_name="schedules")
    op.drop_column("schedules", "timezone")
