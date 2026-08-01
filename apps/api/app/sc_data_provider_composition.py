"""Minimal composition root for the SC data-provider process."""

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


@dataclass
class ScDataProviderSharedInfra:
    db_engine: AsyncEngine
    session_factory: AppDatabaseSessionFactory


@dataclass
class ScDataProviderAppContext:
    shared: ScDataProviderSharedInfra
    injector: Injector
    upstream_reader: GrpcScUpstream


def _required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required SC data-provider configuration: {name}")
    return value


def _build_dataset_storage_factory(
    cfg: AppConfig,
    session_factory: AppDatabaseSessionFactory,
) -> DatasetStorageFactoryPort:
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

    repository = DatasetSqlRepository(session_factory=session_factory.sessionmaker)
    payload_store = DatasetPayloadStore(
        storage=artifact_storage,
        manifest_cache_max_bytes=cfg.storage.sparse_manifest_cache_max_bytes,
    )
    return DatasetStorageFactory(
        repo=repository,
        storage=artifact_storage,
        payload_store=payload_store,
        session_factory=session_factory.sessionmaker,
        prediction_compaction_memory_limit=cfg.prediction.compaction_memory_limit,
        prediction_compaction_temp_limit=cfg.prediction.compaction_temp_limit,
        prediction_compaction_row_group_rows=(cfg.prediction.compaction_row_group_rows),
    )


class _ScDataProviderModule(Module):
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


def build_sc_data_provider_app_context(cfg: AppConfig) -> ScDataProviderAppContext:
    grpc_addr = _required_environment("SC_UPSTREAM_ADDR")
    flight_addr = _required_environment("SC_UPSTREAM_FLIGHT_ADDR")
    db_engine = create_engine(db_url=str(cfg.db.url), echo=bool(cfg.db.echo))
    session_factory = AppDatabaseSessionFactory(create_session_factory(db_engine))
    upstream_reader = GrpcScUpstream(
        grpc_addr=grpc_addr,
        flight_addr=flight_addr,
    )
    injector = Injector(
        [
            _ScDataProviderModule(
                cfg=cfg,
                session_factory=session_factory,
                upstream_reader=upstream_reader,
            )
        ]
    )
    return ScDataProviderAppContext(
        shared=ScDataProviderSharedInfra(
            db_engine=db_engine,
            session_factory=session_factory,
        ),
        injector=injector,
        upstream_reader=upstream_reader,
    )


async def close_sc_data_provider_app_context(
    context: ScDataProviderAppContext,
) -> None:
    try:
        await context.upstream_reader.close()
    finally:
        await context.shared.db_engine.dispose()
