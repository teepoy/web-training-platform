from alembic import op
import sqlalchemy as sa


revision = "f0a1b2c3d4e5"
down_revision = "ef6a7b8c9d0e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("training_jobs") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.String(64), nullable=True))

    with op.batch_alter_table("annotations") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.String(64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("annotations") as batch_op:
        batch_op.drop_column("user_id")

    with op.batch_alter_table("training_jobs") as batch_op:
        batch_op.drop_column("user_id")
