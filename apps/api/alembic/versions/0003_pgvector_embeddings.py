"""Add pgvector extension and embedding_vec column to sample_features

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-03 00:00:00.000000+00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        # Create pgvector extension
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

        # Add embedding_vec column (pgvector Vector type — 512 dimensions)
        op.execute("ALTER TABLE sample_features ADD COLUMN IF NOT EXISTS embedding_vec vector(512)")

        # Add HNSW index for cosine distance
        op.execute("CREATE INDEX IF NOT EXISTS idx_sample_features_embedding_vec ON sample_features USING hnsw (embedding_vec vector_cosine_ops)")

    # Add embed_model and computed_at to sample_features (both dialects)
    op.add_column("sample_features", sa.Column("embed_model", sa.String(255), nullable=True))
    op.add_column("sample_features", sa.Column("computed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.drop_column("sample_features", "computed_at")
    op.drop_column("sample_features", "embed_model")

    if dialect == "postgresql":
        op.execute("DROP INDEX IF EXISTS idx_sample_features_embedding_vec")
        op.execute("ALTER TABLE sample_features DROP COLUMN IF EXISTS embedding_vec")
