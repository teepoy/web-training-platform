"""Migrate image_uri to image_uris

Revision ID: 0002
Revises: 0001_initial_schema
Create Date: 2026-04-01 00:00:00.000000+00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # Add new JSON column
    op.add_column("samples", sa.Column("image_uris", sa.JSON(), nullable=True))

    # Migrate data: wrap existing image_uri in a JSON array
    if dialect == "postgresql":
        op.execute("UPDATE samples SET image_uris = jsonb_build_array(image_uri) WHERE image_uri IS NOT NULL")
    else:
        # SQLite
        op.execute("UPDATE samples SET image_uris = json_array(image_uri)")

    # Drop old column
    op.drop_column("samples", "image_uri")


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.add_column("samples", sa.Column("image_uri", sa.Text(), nullable=True))

    # Take first element from array
    if dialect == "postgresql":
        op.execute("UPDATE samples SET image_uri = image_uris->>0 WHERE image_uris IS NOT NULL")
    else:
        # SQLite
        op.execute("UPDATE samples SET image_uri = json_extract(image_uris, '$[0]')")

    op.drop_column("samples", "image_uris")
