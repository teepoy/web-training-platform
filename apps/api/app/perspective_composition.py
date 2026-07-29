"""Minimal composition root for the Perspective WebSocket process."""

from __future__ import annotations

import os
from dataclasses import dataclass

from injector import Binder, Injector, Module, provider, singleton
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import AppConfig
from app.modules.sc.adapter.grpc_upstream import GrpcScUpstream
from app.modules.sc.domain.upstream_reader import ScUpstreamReader
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.shared.db.session import (
    AppDatabaseSessionFactory,
    create_engine,
    create_session_factory,
)
from app.shared.infrastructure.redis.event_publisher import RedisEventPublisher


@dataclass
class PerspectiveSharedInfra:
    db_engine: AsyncEngine
    session_factory: AppDatabaseSessionFactory
    redis_event_publisher: RedisEventPublisher | None = None


@dataclass
class PerspectiveAppContext:
    shared: PerspectiveSharedInfra
    injector: Injector
    upstream_reader: GrpcScUpstream


def _required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required Perspective configuration: {name}")
    return value


def _build_dataset_storage_factory(
    cfg: AppConfig,
    session_factory: AppDatabaseSessionFactory,
) -> DatasetStorageFactoryPort:
    # Keep dataset-only dependencies out of inspection-only workers until the
    # dataset websocket endpoint is actually used.
    from app.modules.datasets.adapter.repositories.dataset_sql_repository import (
        DatasetSqlRepository,
    )
    from app.modules.storage.adapter.factory import DatasetStorageFactory
    from app.modules.storage.domain.sparse import DatasetPayloadStore
    from app.shared.infrastructure.storage.memory import InMemoryArtifactStorage
    from app.shared.infrastructure.storage.minio import (
        MinioArtifactStorage,
        build_minio_export_lifecycle,
    )

    storage_kind = str(cfg.storage.kind)
    if storage_kind == "memory":
        artifact_storage = InMemoryArtifactStorage()
    elif storage_kind == "minio":
        artifact_storage = MinioArtifactStorage(
            endpoint=str(cfg.storage.minio.endpoint),
            access_key=str(cfg.storage.minio.access_key),
            secret_key=str(cfg.storage.minio.secret_key),
            bucket=str(cfg.storage.minio.bucket),
            secure=bool(cfg.storage.minio.secure),
            export_lifecycle=build_minio_export_lifecycle(cfg),
        )
    else:
        raise RuntimeError(f"Unsupported storage.kind: {storage_kind}")

    repository = DatasetSqlRepository(
        session_factory=session_factory.sessionmaker,
    )
    payload_store = DatasetPayloadStore(storage=artifact_storage)
    return DatasetStorageFactory(
        repo=repository,
        storage=artifact_storage,
        payload_store=payload_store,
        session_factory=session_factory.sessionmaker,
    )


class _PerspectiveModule(Module):
    def __init__(
        self,
        *,
        cfg: AppConfig,
        session_factory: AppDatabaseSessionFactory,
        upstream_reader: GrpcScUpstream,
    ) -> None:
        self._cfg = cfg
        self._session_factory = session_factory
        self._upstream_reader = upstream_reader

    def configure(self, binder: Binder) -> None:
        binder.bind(
            AppDatabaseSessionFactory,
            to=self._session_factory,
            scope=singleton,
        )

    @provider
    @singleton
    def provide_sc_upstream_reader(self) -> ScUpstreamReader:
        return self._upstream_reader

    @provider
    @singleton
    def provide_dataset_storage_factory(self) -> DatasetStorageFactoryPort:
        return _build_dataset_storage_factory(self._cfg, self._session_factory)


def build_perspective_app_context(cfg: AppConfig) -> PerspectiveAppContext:
    grpc_addr = _required_environment("SC_UPSTREAM_ADDR")
    flight_addr = _required_environment("SC_UPSTREAM_FLIGHT_ADDR")
    db_engine = create_engine(
        db_url=str(cfg.db.url),
        echo=bool(cfg.db.echo),
    )
    session_factory = AppDatabaseSessionFactory(create_session_factory(db_engine))
    upstream_reader = GrpcScUpstream(
        grpc_addr=grpc_addr,
        flight_addr=flight_addr,
    )
    injector = Injector(
        [
            _PerspectiveModule(
                cfg=cfg,
                session_factory=session_factory,
                upstream_reader=upstream_reader,
            )
        ]
    )
    return PerspectiveAppContext(
        shared=PerspectiveSharedInfra(
            db_engine=db_engine,
            session_factory=session_factory,
        ),
        injector=injector,
        upstream_reader=upstream_reader,
    )


async def close_perspective_app_context(ctx: PerspectiveAppContext) -> None:
    try:
        await ctx.upstream_reader.close()
    finally:
        await ctx.shared.db_engine.dispose()
