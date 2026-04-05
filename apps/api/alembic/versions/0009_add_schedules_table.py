from alembic import op
import sqlalchemy as sa


revision = "abc2def3abc4"
down_revision = "def3abc4def5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("schedules"):
        return

    op.create_table(
        "schedules",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("org_id", sa.String(64), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("prefect_deployment_id", sa.String(255), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("flow_name", sa.String(255), nullable=False),
        sa.Column("cron", sa.String(255), nullable=True),
        sa.Column("parameters", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("is_schedule_active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def downgrade() -> None:
    op.drop_table("schedules")
