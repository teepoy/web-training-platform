"""add oauth fields to users

Revision ID: 9967d60b337d
Revises: rev0018_platform_preds
Create Date: 2026-05-12 12:35:11.692878

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9967d60b337d'
down_revision = 'rev0018_platform_preds'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add OAuth provider fields
    op.add_column("users", sa.Column("oauth_provider", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("oauth_provider_id", sa.String(length=255), nullable=True))
    # Make hashed_password nullable (OAuth users have no password)
    op.alter_column("users", "hashed_password", existing_type=sa.String(length=255), nullable=True)
    # Unique constraint: one OAuth account per provider
    op.create_unique_constraint("uq_users_oauth_provider_id", "users", ["oauth_provider", "oauth_provider_id"])


def downgrade() -> None:
    op.drop_constraint("uq_users_oauth_provider_id", "users", type_="unique")
    op.alter_column("users", "hashed_password", existing_type=sa.String(length=255), nullable=False)
    op.drop_column("users", "oauth_provider_id")
    op.drop_column("users", "oauth_provider")
