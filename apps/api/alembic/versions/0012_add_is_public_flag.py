from alembic import op
import sqlalchemy as sa


revision = "ef6a7b8c9d0e"
down_revision = "cde5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("datasets") as batch_op:
        batch_op.add_column(sa.Column("is_public", sa.Boolean(), nullable=False, server_default="0"))
    with op.batch_alter_table("training_jobs") as batch_op:
        batch_op.add_column(sa.Column("is_public", sa.Boolean(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("training_jobs") as batch_op:
        batch_op.drop_column("is_public")
    with op.batch_alter_table("datasets") as batch_op:
        batch_op.drop_column("is_public")
