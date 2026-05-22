from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.shared.db.registry import Base
from app.shared.db import registry as _registry  # noqa: F401


def _set_sqlite_pragma(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def create_engine(db_url: str, echo: bool = False) -> AsyncEngine:
    connect_args: dict = {}
    if db_url.startswith("sqlite"):
        connect_args = {"timeout": 30}
    engine = create_async_engine(db_url, echo=echo, connect_args=connect_args)
    if db_url.startswith("sqlite"):
        event.listens_for(engine.sync_engine, "connect")(_set_sqlite_pragma)
    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
