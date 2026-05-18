from __future__ import annotations
# pyright: reportMissingImports=false

from dependency_injector import containers, providers

from app.agent.session_store import SessionStore
from app.agent.surface_store import SurfaceStore
from app.containers.infra import InfraContainer
from app.presets.registry import PresetRegistry
from app.repositories.sensor_repository import SensorRepository
from app.sensors.registry import SensorRegistry
from app.services.artifacts import ArtifactService
from app.services.auth import AuthService
from app.services.engines import KubeflowTrainingOperatorEngine, LocalProcessEngine
from app.services.feature_ops import FeatureOpsService
from app.services.model_service import ModelService
from app.services.notification import WebhookNotificationSink
from app.services.orchestrator import TrainingOrchestrator
from app.services.prediction_orchestrator import PredictionOrchestrator
from app.services.prediction_service import PredictionService
from app.services.prefect_client import PrefectClient
from app.services.prefect_engine import PrefectWorkPoolEngine
from app.services.preview_service import PreviewService
from app.services.preview_store import PreviewStore
from app.services.preview_upstream import (
    MockUpstreamAdapter,
    PreviewUpstreamRouter,
    UpstreamAdapter,
)
from app.services.preview_upstream_s3 import S3ZipPreviewUpstream
from app.services.sample_access_factory import SampleAccessFactory
from app.services.sensor_dispatch import SensorDispatchService
from app.services.service_health import ServiceHealthService
from app.services.task_tracker import TaskTrackerService


class Container(InfraContainer):
    wiring_config = containers.WiringConfiguration(
        modules=[
            "app.routers.task_tracker.router",
            "app.routers.import_parquet.router",
            "app.routers.export_parquet.router",
            "app.routers.auth.router",
            "app.routers.models.router",
            "app.routers.preview.router",
            "app.routers.agent.router",
            "app.routers.sensors.router",
        ],
    )

    # ---- platform ----

    prefect_client = providers.Singleton(
        PrefectClient,
        prefect_api_url=providers.Callable(
            lambda cfg: cfg.prefect.api_url, InfraContainer.config
        ),
    )

    preset_registry = providers.Singleton(
        PresetRegistry,
        presets_dir=providers.Callable(
            lambda cfg: cfg.presets.dir, InfraContainer.config
        ),
        strict=providers.Callable(
            lambda cfg: bool(cfg.presets.strict), InfraContainer.config
        ),
    )

    sensor_registry = providers.Singleton(
        SensorRegistry,
        sensors_dir=providers.Callable(
            lambda cfg: cfg.sensors.dir, InfraContainer.config
        ),
        strict=providers.Callable(
            lambda cfg: bool(cfg.sensors.strict), InfraContainer.config
        ),
    )
    sensor_repository = providers.Singleton(
        SensorRepository,
        session_factory=InfraContainer.session_factory,
    )
    sensor_dispatch = providers.Singleton(
        SensorDispatchService,
        sensor_repository=sensor_repository,
        prefect_client=prefect_client,
    )

    sample_access_factory = providers.Factory(
        SampleAccessFactory,
        repo=InfraContainer.repository,
    )
    service_health = providers.Singleton(
        ServiceHealthService,
        config=InfraContainer.config,
        prefect_client=prefect_client,
        embedding_client=InfraContainer.embedding_service,
    )
    task_tracker = providers.Singleton(
        TaskTrackerService,
        repository=InfraContainer.repository,
        prefect_client=prefect_client,
        config=InfraContainer.config,
    )
    auth_service: providers.Singleton[AuthService] = providers.Singleton(AuthService)

    # ---- training ----

    local_engine = providers.Singleton(
        LocalProcessEngine, storage=InfraContainer.artifact_storage
    )
    kubeflow_engine = providers.Singleton(
        KubeflowTrainingOperatorEngine,
        kubeflow_client=InfraContainer.kubeflow_client,
        image=providers.Callable(lambda cfg: cfg.kubeflow.image, InfraContainer.config),
        storage=InfraContainer.artifact_storage,
    )

    prefect_engine = providers.Singleton(
        PrefectWorkPoolEngine,
        prefect_client=prefect_client,
        work_pool_name=providers.Callable(
            lambda cfg: cfg.prefect.work_pool_name, InfraContainer.config
        ),
        work_pool_type=providers.Callable(
            lambda cfg: cfg.prefect.work_pool_type, InfraContainer.config
        ),
        flow_name=providers.Callable(
            lambda cfg: cfg.prefect.flow_name, InfraContainer.config
        ),
        concurrency_limit=providers.Callable(
            lambda cfg: int(cfg.prefect.concurrency_limit), InfraContainer.config
        ),
        preset_registry=preset_registry,
    )

    execution_engine = providers.Selector(
        providers.Callable(lambda cfg: cfg.execution.engine, InfraContainer.config),
        local=local_engine,
        kubeflow=kubeflow_engine,
        prefect=prefect_engine,
    )

    notification_sink = providers.Singleton(
        WebhookNotificationSink,
        endpoint=providers.Callable(
            lambda cfg: cfg.notification.webhook.endpoint, InfraContainer.config
        ),
        timeout_seconds=providers.Callable(
            lambda cfg: cfg.notification.webhook.timeout_seconds, InfraContainer.config
        ),
    )

    artifacts = providers.Singleton(
        ArtifactService,
        storage=InfraContainer.artifact_storage,
        repository=InfraContainer.repository,
    )
    orchestrator = providers.Singleton(
        TrainingOrchestrator,
        engine=execution_engine,
        notification_sink=notification_sink,
        repository=InfraContainer.repository,
        artifact_service=artifacts,
    )

    # ---- prediction ----

    feature_ops = providers.Singleton(
        FeatureOpsService,
        repository=InfraContainer.repository,
        embedding_service=InfraContainer.embedding_service,
        inference_worker=InfraContainer.inference_worker,
        gpu_worker=InfraContainer.gpu_worker,
    )
    model_service = providers.Singleton(
        ModelService,
        repository=InfraContainer.repository,
        artifact_storage=InfraContainer.artifact_storage,
    )
    prediction_service = providers.Singleton(
        PredictionService,
        repository=InfraContainer.repository,
        artifact_storage=InfraContainer.artifact_storage,
        config=InfraContainer.config,
        embedding_client=InfraContainer.embedding_service,
        llm_client=InfraContainer.llm_client,
        inference_worker=InfraContainer.inference_worker,
        gpu_worker=InfraContainer.gpu_worker,
    )
    prediction_orchestrator = providers.Singleton(
        PredictionOrchestrator,
        prefect_client=prefect_client,
        repository=InfraContainer.repository,
    )

    # ---- agent ----

    surface_store: providers.Singleton[SurfaceStore] = providers.Singleton(SurfaceStore)
    session_store: providers.Singleton[SessionStore] = providers.Singleton(SessionStore)

    # ---- preview ----

    mock_upstream = providers.Singleton(MockUpstreamAdapter)

    @staticmethod
    def _make_s3_upstream() -> S3ZipPreviewUpstream | None:
        try:
            return S3ZipPreviewUpstream()
        except ImportError:
            return None

    s3_upstream = providers.Singleton(_make_s3_upstream)

    @staticmethod
    def _make_upstreams(
        mock: UpstreamAdapter, s3: UpstreamAdapter | None
    ) -> dict[str, UpstreamAdapter]:
        upstreams = {"mock": mock}
        if s3 is not None:
            upstreams["s3"] = s3
        return upstreams

    preview_upstream: providers.Singleton[PreviewUpstreamRouter] = providers.Singleton(
        PreviewUpstreamRouter,
        upstreams=providers.Callable(
            _make_upstreams, mock=mock_upstream, s3=s3_upstream
        ),
    )
    preview_store: providers.Singleton[PreviewStore] = providers.Singleton(PreviewStore)
    preview_service: providers.Singleton[PreviewService] = providers.Singleton(
        PreviewService,
        store=preview_store,
        upstream=preview_upstream,
    )
