"""add sensor subscription and checkpoint tables

Revision ID: f39ebd1b6571
Revises: a2b4ae7f5b18
Create Date: 2026-05-16 13:31:59.632949

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f39ebd1b6571'
down_revision = 'a2b4ae7f5b18'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('sensor_checkpoints',
    sa.Column('sensor_id', sa.String(length=64), nullable=False),
    sa.Column('watermark', sa.JSON(), server_default='{}', nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('sensor_id')
    )
    op.create_table('sensor_subscriptions',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('sensor_id', sa.String(length=64), nullable=False),
    sa.Column('workflow_type', sa.String(length=64), nullable=False),
    sa.Column('filter_config', sa.JSON(), server_default='{}', nullable=False),
    sa.Column('enabled', sa.Boolean(), server_default='1', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('sensor_subscriptions')
    op.drop_table('sensor_checkpoints')
