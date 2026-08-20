"""Composition root. Concrete wiring happens here ONLY. No other module imports this file (except entrypoints: main.py, flow bodies, agent CLI, seed scripts)."""

from __future__ import annotations

from typing import Any, TypeAlias, TypeVar, cast

from injector import Binder, Injector, Module, provider, singleton

from app.core.config import AppConfig
from app.core.settings.container import SettingsContext, SettingsModule
from app.modules.agent.container import AgentContext, AgentModule
from app.modules.automations.container import AutomationsModule
from app.modules.auth.container import AuthContext, AuthModule
from app.modules.dashboard.container import DashboardContext, DashboardModule
from app.modules.dataset_collections.container import (
    DatasetCollectionsContext,
    DatasetCollectionsModule,
)
from app.modules.datasets.container import DatasetsContext, DatasetsModule
from app.modules.jobs.container import JobsContext, JobsModule
from app.shared.infrastructure.storage.memory import InMemoryArtifactStorage
from app.shared.infrastructure.storage.minio import MinioArtifactStorage
from app.modules.models.container import ModelsContext, ModelsModule
from app.modules.prediction.container import PredictionContext, PredictionModule
from app.modules.sc.container import ScContext, ScModule
from app.modules.storage.container import StorageContext, StorageModule
from app.modules.source_discovery.container import SourceDiscoveryModule
from app.modules.training.container import TrainingContext, TrainingModule
from app.modules.datasets.adapter.repositories.dataset_sql_repository import (
    DatasetSqlRepository,
)
from app.shared.domain.protocols import (
    ArtifactStorage as ArtifactStoragePort,
    LabelStudioClient as LabelStudioClientPort,
    NotificationSink as NotificationSinkPort,
    PrefectClient as PrefectClientPort,
)
from app.shared.infrastructure.surface_store import SurfaceStore
from app.shared.context import AppContext, SharedInfra, build_shared_infra
from app.shared.db.session import AppDatabaseSessionFactory

ArtifactStorage: TypeAlias = InMemoryArtifactStorage | MinioArtifactStorage
T = TypeVar("T")


def build_flow_app_context(cfg: AppConfig) -> AppContext:
    """Build AppContext for Prefect flows.

    This returns the same fully wired AppContext used by the FastAPI server
    path, including per-module contexts and injector-bound ports.

    **Lifecycle**: callers MUST invoke :func:`close_flow_app_context` when
    the context is no longer needed to release the DB engine and HTTP
    clients.
    """
    import redis.asyncio as redis_client  # type: ignore[import-untyped]

    from app.shared.infrastructure.redis.event_publisher import RedisEventPublisher

    ctx = build_app_context(cfg)
    redis = redis_client.Redis(
        host=str(cfg.redis.host),
        port=int(cfg.redis.port),
        password=str(cfg.redis.password) if cfg.redis.password else None,
        db=int(cfg.redis.db),
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    ctx.shared.redis_event_publisher = RedisEventPublisher(
        cast(Any, redis),
        revision_namespace=cfg.sc.data_provider.revision_namespace,
    )
    return ctx


async def close_flow_app_context(ctx: AppContext) -> None:
    """Clean up resources held by a flow ``AppContext``.

    Disposes the async SQLAlchemy engine and closes the Prefect HTTP
    client transport.
    """
    try:
        publisher = ctx.shared.redis_event_publisher
        if publisher is not None:
            await publisher.close()
    finally:
        try:
            prefect_close = getattr(ctx.shared.prefect_client, "close", None)
            if prefect_close is not None:
                await prefect_close()
        finally:
            await ctx.shared.db_engine.dispose()


def _required(value: T | None, name: str) -> T:
    if value is None:
        raise RuntimeError(f"AppContext is missing required context: {name}")
    return value


class _AppContextModule(Module):
    """Expose only lifecycle-owned shared objects through injector providers."""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx

    def configure(self, binder: Binder) -> None:
        binder.bind(AppContext, to=self._ctx, scope=singleton)

    @provider
    @singleton
    def provide_shared_infra(self, ctx: AppContext) -> SharedInfra:
        return ctx.shared

    @provider
    @singleton
    def provide_config(self, shared: SharedInfra) -> AppConfig:
        return shared.config

    @provider
    @singleton
    def provide_session_factory(self, shared: SharedInfra) -> AppDatabaseSessionFactory:
        return shared.session_factory

    @provider
    @singleton
    def provide_artifact_storage(self, shared: SharedInfra) -> ArtifactStoragePort:
        return shared.artifact_storage

    @provider
    @singleton
    def provide_label_studio_client(self, shared: SharedInfra) -> LabelStudioClientPort:
        return shared.label_studio_client

    @provider
    @singleton
    def provide_prefect_client(self, shared: SharedInfra) -> PrefectClientPort:
        return shared.prefect_client

    @provider
    @singleton
    def provide_notification_sink(self, shared: SharedInfra) -> NotificationSinkPort:
        return shared.notification_sink

    @provider
    @singleton
    def provide_surface_store(self, shared: SharedInfra) -> SurfaceStore:
        return shared.surface_store


class _SharedPersistenceModule(Module):
    """Shared persistence objects whose identity spans multiple modules."""

    @provider
    @singleton
    def provide_dataset_sql_repository(
        self, session_factory: AppDatabaseSessionFactory
    ) -> DatasetSqlRepository:
        return DatasetSqlRepository(session_factory=session_factory.sessionmaker)


def build_app_context(cfg: AppConfig) -> AppContext:
    """Build AppContext from config - per-module contexts with cross-deps wired."""
    shared = build_shared_infra(cfg)
    ctx = AppContext(shared=shared)
    injector = Injector(
        [
            _AppContextModule(ctx),
            _SharedPersistenceModule(),
            AuthModule(),
            SettingsModule(),
            StorageModule(),
            DatasetsModule(),
            DatasetCollectionsModule(),
            ModelsModule(),
            PredictionModule(),
            TrainingModule(),
            JobsModule(),
            DashboardModule(),
            AgentModule(),
            AutomationsModule(),
            ScModule(),
            SourceDiscoveryModule(),
        ]
    )
    ctx.injector = injector
    ctx.auth = injector.get(AuthContext)
    ctx.settings = injector.get(SettingsContext)
    ctx.storage = injector.get(StorageContext)
    ctx.datasets = injector.get(DatasetsContext)
    ctx.dataset_collections = injector.get(DatasetCollectionsContext)
    ctx.models = injector.get(ModelsContext)
    ctx.prediction = injector.get(PredictionContext)
    ctx.training = injector.get(TrainingContext)
    ctx.jobs = injector.get(JobsContext)
    ctx.dashboard = injector.get(DashboardContext)
    ctx.agent = injector.get(AgentContext)
    ctx.sc = injector.get(ScContext)
    return ctx
