from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.base import Base
from app.db import models as _models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_url() -> str:
    """Resolve the database URL for Alembic migrations.

    Priority:
      1. DATABASE_URL environment variable
      2. APP_CONFIG_PROFILE → load from config YAML
      3. alembic.ini sqlalchemy.url (fallback)

    Alembic uses synchronous drivers, so async URLs are converted:
      postgresql+asyncpg:// → postgresql+psycopg2://
      sqlite+aiosqlite:///  → sqlite:///
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        try:
            from app.core.config import load_config
            cfg = load_config()
            url = cfg.db.url
        except Exception:
            url = config.get_main_option("sqlalchemy.url")

    # Convert async drivers to sync equivalents for Alembic
    if url:
        url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        url = url.replace("sqlite+aiosqlite:///", "sqlite:///")
    return url


def run_migrations_offline() -> None:
    url = _get_url()
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    alembic_cfg = config.get_section(config.config_ini_section, {})
    alembic_cfg["sqlalchemy.url"] = _get_url()

    connectable = engine_from_config(
        alembic_cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
