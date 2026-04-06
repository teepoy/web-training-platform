from __future__ import annotations

import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError


revision = "cde5f6a7b8c9"
down_revision = "bcd4ef5bcd6a"
branch_labels = None
depends_on = None

DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"
SUPERADMIN_USER_ID = "00000000-0000-0000-0000-000000000002"
SUPERADMIN_MEMBERSHIP_ID = "00000000-0000-0000-0000-000000000003"
SUPERADMIN_EMAIL = "admin@localhost"
SUPERADMIN_NAME = "Admin"
SUPERADMIN_HASHED_PASSWORD = "$2b$12$g1sC7UNgLtgeCCBR8UWyzO5EX5JaYnB9OmwChz4SH17EGoBHMYNoy"


def _utc_now_iso() -> str:
    return datetime.datetime.utcnow().isoformat()


def upgrade() -> None:
    created_at = _utc_now_iso()

    try:
        op.execute(
            sa.text(
                f"INSERT INTO users (id, email, name, hashed_password, is_superadmin, is_active, created_at) "
                f"VALUES ('{SUPERADMIN_USER_ID}', '{SUPERADMIN_EMAIL}', '{SUPERADMIN_NAME}', "
                f"'{SUPERADMIN_HASHED_PASSWORD}', TRUE, TRUE, '{created_at}')"
            )
        )
    except IntegrityError:
        pass

    try:
        op.execute(
            sa.text(
                f"INSERT INTO org_memberships (id, user_id, org_id, role, created_at) "
                f"VALUES ('{SUPERADMIN_MEMBERSHIP_ID}', '{SUPERADMIN_USER_ID}', '{DEFAULT_ORG_ID}', 'admin', '{created_at}')"
            )
        )
    except IntegrityError:
        pass


def downgrade() -> None:
    op.execute(
        sa.text(
            f"DELETE FROM org_memberships WHERE user_id = '{SUPERADMIN_USER_ID}'"
        )
    )
    op.execute(
        sa.text(
            f"DELETE FROM users WHERE id = '{SUPERADMIN_USER_ID}'"
        )
    )
