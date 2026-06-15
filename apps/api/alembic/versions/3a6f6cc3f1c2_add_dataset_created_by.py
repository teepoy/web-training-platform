"""add dataset created_by

Revision ID: 3a6f6cc3f1c2
Revises: 8143270e4e25
Create Date: 2026-06-24 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "3a6f6cc3f1c2"
down_revision = "8143270e4e25"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "datasets",
        sa.Column(
            "created_by",
            sa.String(length=255),
            nullable=False,
            server_default="system",
        ),
    )


def downgrade() -> None:
    op.drop_column("datasets", "created_by")
