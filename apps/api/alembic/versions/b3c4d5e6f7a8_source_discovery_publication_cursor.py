"""Use publication cursors and canonical source identity.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "b3c4d5e6f7a8"
down_revision: str | None = "a2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _fail_on_version_duplicates() -> None:
    bind = op.get_bind()
    checks = (
        (
            "collection_import_receipts",
            "collection_id, connector_id, source_record_key, import_profile_version_id",
        ),
        (
            "collection_discovery_receipts",
            "rule_id, connector_id, source_record_key, import_profile_version_id",
        ),
    )
    for table, identity in checks:
        duplicate = bind.execute(
            sa.text(
                f"SELECT 1 FROM {table} GROUP BY {identity} HAVING count(*) > 1 LIMIT 1"
            )
        ).first()
        if duplicate is not None:
            raise RuntimeError(
                f"{table} contains duplicate canonical source identities that differ only "
                "by legacy source_version; remove those duplicates before upgrading"
            )


def upgrade() -> None:
    _fail_on_version_duplicates()
    op.drop_table("collection_membership_suppressions")

    with op.batch_alter_table("collection_discovery_run_items") as batch:
        batch.drop_column("source_version")
    with op.batch_alter_table("collection_import_receipts") as batch:
        batch.drop_constraint("uq_collection_import_identity", type_="unique")
        batch.drop_column("source_version_key")
        batch.create_unique_constraint(
            "uq_collection_import_identity",
            (
                "collection_id",
                "connector_id",
                "source_record_key",
                "import_profile_version_id",
            ),
        )
    with op.batch_alter_table("collection_discovery_receipts") as batch:
        batch.drop_constraint("uq_collection_discovery_receipt", type_="unique")
        batch.drop_column("source_version_key")
        batch.create_unique_constraint(
            "uq_collection_discovery_receipt",
            (
                "rule_id",
                "connector_id",
                "source_record_key",
                "import_profile_version_id",
            ),
        )
    with op.batch_alter_table("collection_source_memberships") as batch:
        batch.drop_column("source_version")


def downgrade() -> None:
    with op.batch_alter_table("collection_source_memberships") as batch:
        batch.add_column(sa.Column("source_version", sa.String(length=512)))
    with op.batch_alter_table("collection_discovery_receipts") as batch:
        batch.drop_constraint("uq_collection_discovery_receipt", type_="unique")
        batch.add_column(
            sa.Column(
                "source_version_key",
                sa.String(length=512),
                nullable=False,
                server_default="",
            )
        )
        batch.create_unique_constraint(
            "uq_collection_discovery_receipt",
            (
                "rule_id",
                "connector_id",
                "source_record_key",
                "source_version_key",
                "import_profile_version_id",
            ),
        )
        batch.alter_column("source_version_key", server_default=None)
    with op.batch_alter_table("collection_import_receipts") as batch:
        batch.drop_constraint("uq_collection_import_identity", type_="unique")
        batch.add_column(
            sa.Column(
                "source_version_key",
                sa.String(length=512),
                nullable=False,
                server_default="",
            )
        )
        batch.create_unique_constraint(
            "uq_collection_import_identity",
            (
                "collection_id",
                "connector_id",
                "source_record_key",
                "source_version_key",
                "import_profile_version_id",
            ),
        )
        batch.alter_column("source_version_key", server_default=None)
    with op.batch_alter_table("collection_discovery_run_items") as batch:
        batch.add_column(sa.Column("source_version", sa.String(length=512)))

    op.create_table(
        "collection_membership_suppressions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("collection_id", sa.String(length=64), nullable=False),
        sa.Column("connector_id", sa.String(length=64), nullable=False),
        sa.Column("source_record_key", sa.String(length=512), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cleared_by", sa.String(length=255)),
        sa.Column("cleared_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ("collection_id",), ("dataset_collections.id",), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ("connector_id",), ("source_connectors.id",), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_collection_membership_suppressions_collection_id",
        "collection_membership_suppressions",
        ("collection_id",),
    )
    op.create_index(
        "uq_collection_active_suppression",
        "collection_membership_suppressions",
        ("collection_id", "connector_id", "source_record_key"),
        unique=True,
        sqlite_where=sa.text("cleared_at IS NULL"),
        postgresql_where=sa.text("cleared_at IS NULL"),
    )
