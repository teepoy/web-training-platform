from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db import models as _models  # noqa: F401


def create_engine(db_url: str, echo: bool = False) -> AsyncEngine:
    connect_args: dict = {}
    if db_url.startswith("sqlite"):
        connect_args = {"timeout": 30}
    return create_async_engine(db_url, echo=echo, connect_args=connect_args)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
