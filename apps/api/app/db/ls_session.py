"""Label Studio database session factory.

Provides an async SQLAlchemy engine and session factory for read-only
access to the Label Studio Postgres database.  Used by
:class:`LsReadRepository` to query tasks and annotations directly.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def create_ls_engine(database_url: str):
    """Create an async engine for the Label Studio database."""
    return create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
    )


def create_ls_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory bound to *engine*."""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
