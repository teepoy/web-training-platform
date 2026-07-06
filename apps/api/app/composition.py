"""Composition root. Concrete wiring happens here ONLY. No other module imports this file (except entrypoints: main.py, flow bodies, agent CLI, seed scripts)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeAlias

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from platform_runtime.sparse import DatasetPayloadStore
from app.modules.sensors.adapter.repositories.repository import (
    SensorRepositoryImpl,
)
from app.modules.sensors.domain.entities.registry import SensorRegistry
from app.modules.settings.adapter.repositories.repository import (
    InMemorySettingsRepository,
)
from app.shared.db.sql_repository import SqlRepository
from app.modules.training.adapter.clients.kubeflow_client import KubeflowClient
from app.modules.training.adapter.engines.local_kubeflow import (
    KubeflowTrainingOperatorEngine,
    LocalProcessEngine,
)
from app.modules.training.adapter.engines.prefect_engine import (
    PrefectWorkPoolEngine,
)
from app.shared.application.notification import WebhookNotificationSink
from app.shared.db.session import create_engine, create_session_factory
from app.shared.infrastructure.label_studio.client import LabelStudioClient
from app.shared.infrastructure.llm.client import OpenAICompatibleLlmClient
from app.shared.infrastructure.prefect.client import PrefectClient
from app.shared.infrastructure.storage.memory import InMemoryArtifactStorage
from app.shared.infrastructure.storage.minio import (
    MinioArtifactStorage,
    build_minio_export_lifecycle,
)
from app.modules.dashboard.app.services.service_health import (
    ServiceHealthService,
)
from app.modules.models.adapter.repositories.repository import (
    ModelArtifactRepository,
)
from app.modules.preview.app.services.preview_store import PreviewStore
from app.modules.preview.app.services.preview_upstream import (
    MockUpstreamAdapter,
    PreviewUpstreamRouter,
    UpstreamAdapter,
)
from app.modules.prediction.app.services.prediction_orchestrator import (
    PredictionOrchestrator,
)
from app.modules.prediction.domain.repository import PredictionRepository
from app.modules.models.app.services.model_service import ModelService
from app.modules.schedules.app.services.scheduler import SchedulerService
from app.modules.training.app.services.orchestrator import TrainingOrchestrator
from app.shared.application.artifacts import ArtifactService
from app.shared.infrastructure.surface_store import SurfaceStore
from app.modules.agent.app.services.session_store import SessionStore
from app.shared.context import AppContext, build_shared_infra

# Per-module container factories
from app.modules.datasets.container import init_datasets
from app.modules.prediction.container import init_prediction
from app.modules.training.container import init_training
from app.modules.models.container import init_models
from app.modules.dashboard.container import init_dashboard
from app.modules.preview.container import init_preview
from app.modules.task_tracker.container import init_task_tracker
from app.modules.schedules.container import init_schedules
from app.modules.sensors.container import init_sensors
from app.modules.settings.container import init_settings
from app.modules.agent.container import init_agent
from app.modules.classify.container import init_classify
from app.modules.auth.container import init_auth
from app.modules.sc.container import init_sc

AppConfig: TypeAlias = Any
ArtifactStorage: TypeAlias = InMemoryArtifactStorage | MinioArtifactStorage
TrainingExecutionEngine: TypeAlias = (
    LocalProcessEngine | KubeflowTrainingOperatorEngine | PrefectWorkPoolEngine
)


@dataclass
class AppContainer:
    config: AppConfig
    db_engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    artifact_storage: ArtifactStorage
    label_studio_client: LabelStudioClient
    llm_client: OpenAICompatibleLlmClient
    prefect_client: PrefectClient
    kubeflow_client: KubeflowClient | None
    notification_sink: WebhookNotificationSink
    training_engine: TrainingExecutionEngine
    training_orchestrator: TrainingOrchestrator
    sensor_registry: SensorRegistry
    sensor_repository: SensorRepositoryImpl
    settings_repository: InMemorySettingsRepository
    task_tracker_repository: SqlRepository
    service_health_service: ServiceHealthService
    model_repository: ModelArtifactRepository
    prediction_repository: PredictionRepository
    dataset_repository: SqlRepository
    dataset_payload_store: DatasetPayloadStore
    preview_store: PreviewStore
    preview_upstream: UpstreamAdapter
    prediction_orchestrator: PredictionOrchestrator
    scheduler_service: SchedulerService
    model_service: ModelService
    surface_store: SurfaceStore
    session_store: SessionStore

    async def close(self) -> None:
        prefect_close = getattr(self.prefect_client, "close", None)
        if prefect_close is not None:
            await prefect_close()
        await self.db_engine.dispose()


def _build_artifact_storage(cfg: AppConfig) -> ArtifactStorage:
    kind = str(cfg.storage.kind)
    if kind == "memory":
        return InMemoryArtifactStorage()
    if kind == "minio":
        return MinioArtifactStorage(
            endpoint=str(cfg.storage.minio.endpoint),
            access_key=str(cfg.storage.minio.access_key),
            secret_key=str(cfg.storage.minio.secret_key),
            bucket=str(cfg.storage.minio.bucket),
            secure=bool(cfg.storage.minio.secure),
            export_lifecycle=build_minio_export_lifecycle(cfg),
        )
    raise RuntimeError(f"Unsupported storage.kind: {kind}")


def _build_kubeflow_client(cfg: AppConfig) -> KubeflowClient:
    return KubeflowClient(
        namespace=str(cfg.k8s.namespace),
        group=str(cfg.kubeflow.group),
        version=str(cfg.kubeflow.version),
        plural=str(cfg.kubeflow.plural),
        in_cluster=bool(cfg.k8s.incluster),
        kubeconfig=str(cfg.k8s.kubeconfig),
    )


def _build_training_engine(
    cfg: AppConfig,
    artifact_storage: ArtifactStorage,
    prefect_client: PrefectClient,
    kubeflow_client: KubeflowClient | None,
) -> TrainingExecutionEngine:
    engine = str(cfg.execution.engine)
    if engine == "local":
        return LocalProcessEngine(storage=artifact_storage)
    if engine == "kubeflow":
        return KubeflowTrainingOperatorEngine(
            kubeflow_client=kubeflow_client,
            image=str(cfg.kubeflow.image),
            storage=artifact_storage,
        )
    if engine == "prefect":
        return PrefectWorkPoolEngine(
            prefect_client=prefect_client,
            work_pool_name=str(cfg.prefect.work_pool_name),
            work_pool_type=str(cfg.prefect.work_pool_type),
            flow_name=str(cfg.prefect.flow_name),
            concurrency_limit=int(cfg.prefect.concurrency_limit),
        )
    raise RuntimeError(f"Unsupported execution.engine: {engine}")


def _build_base_container(cfg: AppConfig) -> AppContainer:
    db_engine = create_engine(
        db_url=str(cfg.db.url),
        echo=bool(cfg.db.echo),
    )
    session_factory = create_session_factory(db_engine)
    artifact_storage = _build_artifact_storage(cfg)
    prefect_client = PrefectClient(prefect_api_url=str(cfg.prefect.api_url))
    kubeflow_client = (
        _build_kubeflow_client(cfg) if str(cfg.execution.engine) == "kubeflow" else None
    )
    prediction_repository = SqlRepository(session_factory=session_factory)
    dataset_repository = SqlRepository(session_factory=session_factory)
    notification_sink = WebhookNotificationSink(
        endpoint=str(cfg.notification.webhook.endpoint),
        timeout_seconds=int(cfg.notification.webhook.timeout_seconds),
    )
    training_engine = _build_training_engine(
        cfg=cfg,
        artifact_storage=artifact_storage,
        prefect_client=prefect_client,
        kubeflow_client=kubeflow_client,
    )
    artifact_service = ArtifactService(
        storage=artifact_storage,
        repository=prediction_repository,
    )
    return AppContainer(
        config=cfg,
        db_engine=db_engine,
        session_factory=session_factory,
        artifact_storage=artifact_storage,
        label_studio_client=LabelStudioClient(
            url=str(cfg.label_studio.url),
            api_key=str(cfg.label_studio.api_key),
        ),
        llm_client=OpenAICompatibleLlmClient(
            base_url=str(cfg.llm.base_url),
            api_key=str(cfg.llm.api_key),
            model=str(cfg.llm.model),
            timeout_seconds=float(cfg.llm.timeout_seconds),
        ),
        prefect_client=prefect_client,
        kubeflow_client=kubeflow_client,
        notification_sink=notification_sink,
        training_engine=training_engine,
        training_orchestrator=TrainingOrchestrator(
            engine=training_engine,
            notification_sink=notification_sink,
            repository=prediction_repository,
            artifact_service=artifact_service,
        ),
        sensor_registry=SensorRegistry(
            sensors_dir=str(Path(cfg.data.dir) / cfg.sensors.dir)
            if cfg.data.dir
            else str(cfg.sensors.dir),
            strict=bool(cfg.sensors.strict),
        ),
        sensor_repository=SensorRepositoryImpl(session_factory=session_factory),
        settings_repository=InMemorySettingsRepository(),
        task_tracker_repository=SqlRepository(session_factory=session_factory),
        service_health_service=ServiceHealthService(
            config=cfg,
            prefect_client=prefect_client,
        ),
        model_repository=ModelArtifactRepository(session_factory=session_factory),
        prediction_repository=prediction_repository,
        dataset_repository=dataset_repository,
        dataset_payload_store=DatasetPayloadStore(storage=artifact_storage),
        preview_store=PreviewStore(),
        preview_upstream=PreviewUpstreamRouter(
            upstreams={"mock": MockUpstreamAdapter()}
        ),
        prediction_orchestrator=PredictionOrchestrator(
            prefect_client=prefect_client,
            repository=prediction_repository,
        ),
        scheduler_service=SchedulerService(
            prefect_client=prefect_client,
            repository=SqlRepository(session_factory=session_factory),
        ),
        model_service=ModelService(
            repository=ModelArtifactRepository(session_factory=session_factory),
            artifact_storage=artifact_storage,
        ),
        surface_store=SurfaceStore(),
        session_store=SessionStore(),
    )


def build_flow_container(cfg: AppConfig) -> AppContainer:
    """Legacy flow container — returns flat AppContainer without per-module contexts.

    Prefer :func:`build_flow_app_context` for new Prefect flows that need
    per-module dependencies (e.g. SC repository, upstream reader,
    image fetcher).  This function is kept for backward compatibility
    with flows that only reference shared infra fields on AppContainer.
    """
    return _build_base_container(cfg)


def build_flow_app_context(cfg: AppConfig) -> AppContext:
    """Build AppContext for Prefect flows — full per-module context wiring.

    Unlike ``build_flow_container()`` which returns a legacy flat
    AppContainer, this returns an ``AppContext`` whose ``.sc``,
    ``.datasets``, etc. fields are fully populated by the same per-module
    ``init_*()`` factories used in the FastAPI server path.

    Prefect flows that need SC module dependencies should use this
    entrypoint and access them via ``ctx.sc.repository``,
    ``ctx.sc.upstream_reader``, ``ctx.sc.image_fetcher`` etc. — no local
    ``_build_sc_*`` helpers required.

    **Lifecycle**: callers MUST invoke :func:`close_flow_app_context` when
    the context is no longer needed to release the DB engine and HTTP
    clients.
    """
    return build_app_context(cfg)


async def close_flow_app_context(ctx: AppContext) -> None:
    """Clean up resources held by a flow ``AppContext``.

    Disposes the async SQLAlchemy engine and closes the Prefect HTTP
    client transport.
    """
    prefect_close = getattr(ctx.shared.prefect_client, "close", None)
    if prefect_close is not None:
        await prefect_close()
    await ctx.shared.db_engine.dispose()


def build_app_context(cfg: AppConfig) -> AppContext:
    """Build AppContext from config - per-module contexts with cross-deps wired."""
    shared = build_shared_infra(cfg)

    # Level 0: no cross-deps
    auth = init_auth(shared)
    settings = init_settings(shared)
    models = init_models(shared)
    preview = init_preview(shared)
    sensors = init_sensors(shared)

    # Level 0 but depends on shared infra only
    datasets = init_datasets(shared)

    # Level 0: prediction (needs dataset_service from datasets)
    prediction = init_prediction(
        shared,
        dataset_service=datasets.dataset_service,
        dataset_storage_factory=datasets.dataset_storage_factory,
    )

    # Level 1: one cross-dep
    # task_tracker creates its own repo, exposes it
    task_tracker = init_task_tracker(shared)
    # schedules needs task_tracker_repository
    schedules = init_schedules(
        shared, task_tracker_repository=task_tracker.task_tracker_repository
    )
    # training needs prediction repository port + sample_access_factory (from datasets)
    training = init_training(
        shared,
    )

    # Level 2: multiple cross-deps
    dashboard = init_dashboard(
        shared,
        task_tracker_port=task_tracker.task_tracker_port,
    )
    classify = init_classify(shared)
    agent = init_agent(shared)

    # Level 3: SC module
    from app.modules.sc.adapter.sparse_aware_reader import SparseAwareScDatasetReader

    sc_dataset_reader = SparseAwareScDatasetReader(
        underlying=datasets.dataset_reader,
        storage_factory=datasets.dataset_storage_factory,
    )
    sc = init_sc(
        shared,
        dataset_reader=sc_dataset_reader,
        dataset_payload_store=datasets.dataset_payload_store,
        storage_factory=datasets.dataset_storage_factory,
    )

    return AppContext(
        shared=shared,
        auth=auth,
        settings=settings,
        datasets=datasets,
        models=models,
        preview=preview,
        prediction=prediction,
        sensors=sensors,
        schedules=schedules,
        task_tracker=task_tracker,
        training=training,
        dashboard=dashboard,
        classify=classify,
        agent=agent,
        sc=sc,
    )
