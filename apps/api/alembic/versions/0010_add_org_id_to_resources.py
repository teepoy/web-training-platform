from alembic import op
import sqlalchemy as sa


revision = "bcd4ef5bcd6a"
down_revision = "abc2def3abc4"
branch_labels = None
depends_on = None

DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_ORG_SLUG = "default"
DEFAULT_ORG_NAME = "Default"


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        conn.execute(
            sa.text(
                "INSERT OR IGNORE INTO organizations (id, name, slug, created_at) "
                "VALUES (:id, :name, :slug, CURRENT_TIMESTAMP)"
            ),
            {"id": DEFAULT_ORG_ID, "name": DEFAULT_ORG_NAME, "slug": DEFAULT_ORG_SLUG},
        )
    else:
        conn.execute(
            sa.text(
                "INSERT INTO organizations (id, name, slug, created_at) "
                "VALUES (:id, :name, :slug, CURRENT_TIMESTAMP) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"id": DEFAULT_ORG_ID, "name": DEFAULT_ORG_NAME, "slug": DEFAULT_ORG_SLUG},
        )

    default_org_default = sa.text(f"'{DEFAULT_ORG_ID}'")

    with op.batch_alter_table("datasets", recreate="auto") as batch_op:
        batch_op.add_column(sa.Column("org_id", sa.String(64), nullable=False, server_default=default_org_default))
        batch_op.create_foreign_key("fk_datasets_org_id", "organizations", ["org_id"], ["id"])

    with op.batch_alter_table("training_presets", recreate="auto") as batch_op:
        batch_op.add_column(sa.Column("org_id", sa.String(64), nullable=False, server_default=default_org_default))
        batch_op.create_foreign_key("fk_training_presets_org_id", "organizations", ["org_id"], ["id"])

    with op.batch_alter_table("training_jobs", recreate="auto") as batch_op:
        batch_op.add_column(sa.Column("org_id", sa.String(64), nullable=False, server_default=default_org_default))
        batch_op.create_foreign_key("fk_training_jobs_org_id", "organizations", ["org_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("training_jobs") as batch_op:
        batch_op.drop_column("org_id")
    with op.batch_alter_table("training_presets") as batch_op:
        batch_op.drop_column("org_id")
    with op.batch_alter_table("datasets") as batch_op:
        batch_op.drop_column("org_id")
