from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig

from app.core.config import load_config

_API_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    profile = os.getenv("APP_CONFIG_PROFILE", "")
    if profile not in {"dev", "test"}:
        raise RuntimeError("reset_dev_database requires APP_CONFIG_PROFILE=dev or test")
    if os.getenv("ALLOW_RESET_APP_DATA") != "1":
        raise RuntimeError("reset_dev_database requires ALLOW_RESET_APP_DATA=1")
    load_config()
    alembic = AlembicConfig(str(_API_ROOT / "alembic.ini"))
    command.downgrade(alembic, "base")
    command.upgrade(alembic, "head")
    print(f"Database reset and migrated to head for profile {profile!r}")


if __name__ == "__main__":
    main()
