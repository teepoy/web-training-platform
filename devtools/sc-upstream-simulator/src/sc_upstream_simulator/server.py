from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sc_upstream.direct_cache import DirectMetadataCache
from sc_upstream.server import start_servers

from .api import create_control_app
from .artifacts import BotoObjectStore, InspectionArtifactPublisher
from .repository import SimulatorRepository
from .settings import SimulatorSettings
from .scenarios import ShowcaseScenarioRunner
from .upstream_adapter import SimulatorUpstreamAdapter


def create_app() -> FastAPI:
    settings = SimulatorSettings.from_environment()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        adapter = SimulatorUpstreamAdapter(
            sessions,
            database_url=settings.database_url,
        )
        running = await start_servers(
            upstream=adapter,
            zips=adapter,
            metadata_cache=DirectMetadataCache(),
            flight_cache=None,
            grpc_port=settings.grpc_port,
            flight_port=settings.flight_port,
        )
        try:
            yield
        finally:
            await running.stop()
            adapter.close()
            await engine.dispose()

    repository = SimulatorRepository(sessions)
    object_store = BotoObjectStore(
        endpoint_url=settings.object_store_endpoint,
        access_key=settings.object_store_access_key,
        secret_key=settings.object_store_secret_key,
        region=settings.object_store_region,
    )
    scenario_runner = ShowcaseScenarioRunner(
        repository=repository,
        artifacts=InspectionArtifactPublisher(
            object_store=object_store,
            patch_bucket=settings.patch_bucket,
            review_bucket=settings.review_bucket,
        ),
    )
    return create_control_app(
        repository=repository,
        api_token=settings.api_token,
        scenario_runner=scenario_runner,
        lifespan=lifespan,
    )
