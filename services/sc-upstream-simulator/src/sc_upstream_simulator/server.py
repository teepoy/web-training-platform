from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .api import create_control_app
from .repository import SimulatorRepository
from .settings import SimulatorSettings


def create_app() -> FastAPI:
    settings = SimulatorSettings.from_environment()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        await engine.dispose()

    return create_control_app(
        repository=SimulatorRepository(sessions),
        api_token=settings.api_token,
        lifespan=lifespan,
    )
