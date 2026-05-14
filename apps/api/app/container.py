from __future__ import annotations
# pyright: reportMissingImports=false

from dependency_injector import containers, providers

from app.container_modules.infra import InfraContainer
from app.container_modules.datasets import ContainerDatasets
from app.container_modules.training import ContainerTraining
from app.container_modules.prediction import ContainerPrediction
from app.container_modules.agent import ContainerAgent
from app.container_modules.preview import ContainerPreview
from app.container_modules.platform import ContainerPlatform

from app.services.feature_ops import FeatureOpsService
from app.services.artifacts import ArtifactService
from app.services.engines import KubeflowTrainingOperatorEngine, LocalProcessEngine
from app.services.prefect_engine import PrefectWorkPoolEngine
from app.services.kubeflow_client import KubeflowClient
from app.services.model_service import ModelService
from app.services.orchestrator import TrainingOrchestrator
from app.services.prediction_service import PredictionService
from app.services.prediction_orchestrator import PredictionOrchestrator
from app.services.service_health import ServiceHealthService
from app.services.task_tracker import TaskTrackerService
from app.services.auth import AuthService
from app.agent.session_store import SessionStore
from app.agent.surface_store import SurfaceStore
from app.services.preview_service import PreviewService
from app.services.preview_store import PreviewStore
from app.services.preview_upstream import MockUpstreamAdapter, PreviewUpstreamRouter
from app.services.preview_upstream_s3 import S3ZipPreviewUpstream


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(modules=["app.main"])

    infra = providers.Container(InfraContainer)
    datasets = providers.Container(ContainerDatasets)
    training = providers.Container(ContainerTraining)
    prediction = providers.Container(ContainerPrediction)
    agent = providers.Container(ContainerAgent)
    preview = providers.Container(ContainerPreview)
    platform = providers.Container(ContainerPlatform)

    def __new__(cls):
        obj = super().__new__(cls)
        _wire_domain_providers(obj)
        return obj


def _wire_domain_providers(container: Container) -> None:
    infra = container.infra

    container.datasets().feature_ops = providers.Singleton(
        FeatureOpsService,
        repository=infra.repository,
        embedding_service=infra.embedding_service,
        inference_worker=infra.inference_worker,
    )
    container.datasets().artifacts = providers.Singleton(
        ArtifactService,
        storage=infra.artifact_storage,
        repository=infra.repository,
    )

    kubeflow_client = providers.Factory(
        KubeflowClient,
        namespace=providers.Callable(lambda cfg: cfg.k8s.namespace, infra.config),
        group=providers.Callable(lambda cfg: cfg.kubeflow.group, infra.config),
        version=providers.Callable(lambda cfg: cfg.kubeflow.version, infra.config),
        plural=providers.Callable(lambda cfg: cfg.kubeflow.plural, infra.config),
        in_cluster=providers.Callable(
            lambda cfg: bool(cfg.k8s.incluster), infra.config
        ),
        kubeconfig=providers.Callable(lambda cfg: cfg.k8s.kubeconfig, infra.config),
    )

    local_engine = providers.Singleton(
        LocalProcessEngine, storage=infra.artifact_storage
    )
    kubeflow_engine = providers.Singleton(
        KubeflowTrainingOperatorEngine,
        kubeflow_client=kubeflow_client,
        image=providers.Callable(lambda cfg: cfg.kubeflow.image, infra.config),
        storage=infra.artifact_storage,
    )

    prefect_engine = providers.Singleton(
        PrefectWorkPoolEngine,
        prefect_client=infra.prefect_client,
        work_pool_name=providers.Callable(
            lambda cfg: cfg.prefect.work_pool_name, infra.config
        ),
        work_pool_type=providers.Callable(
            lambda cfg: cfg.prefect.work_pool_type, infra.config
        ),
        flow_name=providers.Callable(lambda cfg: cfg.prefect.flow_name, infra.config),
        concurrency_limit=providers.Callable(
            lambda cfg: int(cfg.prefect.concurrency_limit), infra.config
        ),
        preset_registry=infra.preset_registry,
    )

    execution_engine = providers.Selector(
        providers.Callable(lambda cfg: cfg.execution.engine, infra.config),
        local=local_engine,
        kubeflow=kubeflow_engine,
        prefect=prefect_engine,
    )

    computed_artifacts = providers.Singleton(
        ArtifactService,
        storage=infra.artifact_storage,
        repository=infra.repository,
    )

    container.training().orchestrator = providers.Singleton(
        TrainingOrchestrator,
        engine=execution_engine,
        notification_sink=infra.notification_sink,
        repository=infra.repository,
        artifact_service=computed_artifacts,
    )
    container.training().model_service = providers.Singleton(
        ModelService,
        repository=infra.repository,
        artifact_storage=infra.artifact_storage,
    )

    container.prediction().prediction_service = providers.Singleton(
        PredictionService,
        repository=infra.repository,
        artifact_storage=infra.artifact_storage,
        config=infra.config,
        embedding_client=infra.embedding_service,
        llm_client=infra.llm_client,
        inference_worker=infra.inference_worker,
    )
    container.prediction().prediction_orchestrator = providers.Singleton(
        PredictionOrchestrator,
        prefect_client=infra.prefect_client,
        repository=infra.repository,
    )

    container.agent().surface_store = providers.Singleton(SurfaceStore)
    container.agent().session_store = providers.Singleton(SessionStore)

    mock_upstream = providers.Singleton(MockUpstreamAdapter)

    def _make_s3_upstream():
        try:
            return S3ZipPreviewUpstream()
        except ImportError:
            return None

    s3_upstream = providers.Singleton(_make_s3_upstream)

    def _make_upstreams(mock, s3):
        upstreams = {"mock": mock}
        if s3 is not None:
            upstreams["s3"] = s3
        return upstreams

    container.preview().preview_upstream = providers.Singleton(
        PreviewUpstreamRouter,
        upstreams=providers.Callable(
            _make_upstreams, mock=mock_upstream, s3=s3_upstream
        ),
    )
    container.preview().preview_store = providers.Singleton(PreviewStore)
    container.preview().preview_service = providers.Singleton(
        PreviewService,
        store=container.preview().preview_store,
        upstream=container.preview().preview_upstream,
    )

    container.platform().auth_service = providers.Singleton(AuthService)
    container.platform().service_health = providers.Singleton(
        ServiceHealthService,
        config=infra.config,
        prefect_client=infra.prefect_client,
        embedding_client=infra.embedding_service,
    )
    container.platform().task_tracker = providers.Singleton(
        TaskTrackerService,
        repository=infra.repository,
        prefect_client=infra.prefect_client,
        config=infra.config,
    )
