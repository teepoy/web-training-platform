"""Composition root. Concrete wiring happens here ONLY. No other module imports this file (except entrypoints: main.py, flow bodies, agent CLI, seed scripts)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeAlias

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import _resolve_gpu_worker_url
from app.modules.presets.registry import PresetRegistry
from app.modules.sensors.infrastructure.repositories.repository import (
    SensorRepositoryImpl,
)
from app.modules.settings.infrastructure.repositories.repository import (
    InMemorySettingsRepository,
)
from app.shared.db.sql_repository import SqlRepository
from app.modules.training.infrastructure.clients.kubeflow_client import KubeflowClient
from app.modules.training.infrastructure.engines.local_kubeflow import (
    KubeflowTrainingOperatorEngine,
    LocalProcessEngine,
)
from app.modules.training.infrastructure.engines.prefect_engine import (
    PrefectWorkPoolEngine,
)
from app.shared.application.notification import WebhookNotificationSink
from app.shared.db.session import create_engine, create_session_factory
from app.shared.infrastructure.label_studio.client import LabelStudioClient
from app.shared.infrastructure.llm.client import OpenAICompatibleLlmClient
from app.shared.infrastructure.prefect.client import PrefectClient
from app.shared.infrastructure.storage.memory import InMemoryArtifactStorage
from app.shared.infrastructure.storage.minio import MinioArtifactStorage
from app.shared.infrastructure.workers.embedding import EmbeddingClient
from app.shared.infrastructure.workers.gpu_worker import GpuWorkerClient
from app.shared.infrastructure.workers.inference_worker import InferenceWorkerClient
from app.modules.dashboard.application.services.service_health import (
    ServiceHealthService,
)
from app.modules.models.infrastructure.repositories.repository import (
    ModelArtifactRepository,
)
from app.modules.preview.application.services.preview_store import PreviewStore
from app.modules.preview.application.services.preview_upstream import (
    MockUpstreamAdapter,
    PreviewUpstreamRouter,
    UpstreamAdapter,
)
from app.modules.prediction.domain.repository import PredictionRepository

AppConfig: TypeAlias = Any
ArtifactStorage: TypeAlias = InMemoryArtifactStorage | MinioArtifactStorage
TrainingExecutionEngine: TypeAlias = (
    LocalProcessEngine | KubeflowTrainingOperatorEngine | PrefectWorkPoolEngine
)


@dataclass
class AppContainer:
    config: AppConfig
    session_factory: async_sessionmaker[AsyncSession]
    artifact_storage: ArtifactStorage
    label_studio_client: LabelStudioClient
    llm_client: OpenAICompatibleLlmClient
    prefect_client: PrefectClient
    embedding_client: EmbeddingClient
    inference_worker: InferenceWorkerClient
    gpu_worker: GpuWorkerClient
    kubeflow_client: KubeflowClient | None
    notification_sink: WebhookNotificationSink
    training_engine: TrainingExecutionEngine
    sensor_repository: SensorRepositoryImpl
    settings_repository: InMemorySettingsRepository
    task_tracker_repository: SqlRepository
    service_health_service: ServiceHealthService
    model_repository: ModelArtifactRepository
    prediction_repository: PredictionRepository
    preset_registry: PresetRegistry
    preview_store: PreviewStore
    preview_upstream: UpstreamAdapter

    async def close(self) -> None:
        await self.prefect_client.close()
        self.embedding_client.close()


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
        preset_registry = PresetRegistry(
            presets_dir=str(cfg.presets.dir),
            strict=bool(cfg.presets.strict),
        )
        return PrefectWorkPoolEngine(
            prefect_client=prefect_client,
            work_pool_name=str(cfg.prefect.work_pool_name),
            work_pool_type=str(cfg.prefect.work_pool_type),
            flow_name=str(cfg.prefect.flow_name),
            concurrency_limit=int(cfg.prefect.concurrency_limit),
            preset_registry=preset_registry,
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
    return AppContainer(
        config=cfg,
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
        embedding_client=EmbeddingClient(
            grpc_target=str(cfg.embedding.grpc_target),
        ),
        inference_worker=InferenceWorkerClient(
            base_url=str(cfg.inference.base_url),
        ),
        gpu_worker=GpuWorkerClient(base_url=_resolve_gpu_worker_url(cfg)),
        kubeflow_client=kubeflow_client,
        notification_sink=WebhookNotificationSink(
            endpoint=str(cfg.notification.webhook.endpoint),
            timeout_seconds=int(cfg.notification.webhook.timeout_seconds),
        ),
        training_engine=_build_training_engine(
            cfg=cfg,
            artifact_storage=artifact_storage,
            prefect_client=prefect_client,
            kubeflow_client=kubeflow_client,
        ),
        sensor_repository=SensorRepositoryImpl(session_factory=session_factory),
        settings_repository=InMemorySettingsRepository(),
        task_tracker_repository=SqlRepository(session_factory=session_factory),
        service_health_service=ServiceHealthService(
            config=cfg,
            prefect_client=prefect_client,
            embedding_client=EmbeddingClient(
                grpc_target=str(cfg.embedding.grpc_target)
            ),
        ),
        model_repository=ModelArtifactRepository(session_factory=session_factory),
        prediction_repository=SqlRepository(session_factory=session_factory),
        preset_registry=PresetRegistry(
            presets_dir=str(cfg.presets.dir),
            strict=bool(cfg.presets.strict),
        ),
        preview_store=PreviewStore(),
        preview_upstream=PreviewUpstreamRouter(
            upstreams={"mock": MockUpstreamAdapter()}
        ),
    )


def build_app_container(cfg: AppConfig) -> AppContainer:
    return _build_base_container(cfg)


def build_flow_container(cfg: AppConfig) -> AppContainer:
    return _build_base_container(cfg)


def build_agent_container(cfg: AppConfig) -> AppContainer:
    return _build_base_container(cfg)


def build_cli_container(cfg: AppConfig) -> AppContainer:
    return _build_base_container(cfg)
