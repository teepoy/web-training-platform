from __future__ import annotations

from dependency_injector import containers, providers

from app.core.config import load_config
from app.db.session import create_engine, create_session_factory
from app.repositories.sql_repository import SqlRepository
from app.services.engines import KubeflowTrainingOperatorEngine, LocalProcessEngine
from app.services.prefect_client import PrefectClient
from app.services.prefect_engine import PrefectWorkPoolEngine
from app.services.artifacts import ArtifactService
from app.services.embedding import EmbeddingClient
from app.services.llm import OpenAICompatibleLlmClient
from app.services.feature_ops import FeatureOpsService
from app.services.inference_worker import InferenceWorkerClient
from app.services.kubeflow_client import KubeflowClient
from app.services.label_studio import LabelStudioClient
from app.services.model_service import ModelService
from app.services.notification import WebhookNotificationSink
from app.services.orchestrator import TrainingOrchestrator
from app.services.prediction_service import PredictionService
from app.services.prediction_orchestrator import PredictionOrchestrator
from app.services.service_health import ServiceHealthService
from app.services.auth import AuthService
from app.storage.minio_storage import InMemoryArtifactStorage, MinioArtifactStorage
from app.db.ls_session import create_ls_engine, create_ls_session_factory
from app.repositories.ls_read_repository import LsReadRepository
from app.presets.registry import PresetRegistry


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(modules=["app.main"])

    config = providers.Singleton(load_config)

    db_engine = providers.Singleton(
        create_engine,
        db_url=providers.Callable(lambda cfg: cfg.db.url, config),
        echo=providers.Callable(lambda cfg: bool(cfg.db.echo), config),
    )
    session_factory = providers.Singleton(create_session_factory, engine=db_engine)
    repository = providers.Singleton(SqlRepository, session_factory=session_factory)

    minio_storage = providers.Singleton(
        MinioArtifactStorage,
        endpoint=providers.Callable(lambda cfg: cfg.storage.minio.endpoint, config),
        access_key=providers.Callable(lambda cfg: cfg.storage.minio.access_key, config),
        secret_key=providers.Callable(lambda cfg: cfg.storage.minio.secret_key, config),
        bucket=providers.Callable(lambda cfg: cfg.storage.minio.bucket, config),
        secure=providers.Callable(lambda cfg: bool(cfg.storage.minio.secure), config),
    )
    memory_storage = providers.Singleton(InMemoryArtifactStorage)
    artifact_storage = providers.Selector(
        providers.Callable(lambda cfg: cfg.storage.kind, config),
        memory=memory_storage,
        minio=minio_storage,
    )

    kubeflow_client = providers.Factory(
        KubeflowClient,
        namespace=providers.Callable(lambda cfg: cfg.k8s.namespace, config),
        group=providers.Callable(lambda cfg: cfg.kubeflow.group, config),
        version=providers.Callable(lambda cfg: cfg.kubeflow.version, config),
        plural=providers.Callable(lambda cfg: cfg.kubeflow.plural, config),
        in_cluster=providers.Callable(lambda cfg: bool(cfg.k8s.incluster), config),
        kubeconfig=providers.Callable(lambda cfg: cfg.k8s.kubeconfig, config),
    )

    local_engine = providers.Singleton(LocalProcessEngine, storage=artifact_storage)
    kubeflow_engine = providers.Singleton(
        KubeflowTrainingOperatorEngine,
        kubeflow_client=kubeflow_client,
        image=providers.Callable(lambda cfg: cfg.kubeflow.image, config),
        storage=artifact_storage,
    )

    prefect_client = providers.Singleton(
        PrefectClient,
        prefect_api_url=providers.Callable(lambda cfg: cfg.prefect.api_url, config),
    )

    preset_registry = providers.Singleton(
        PresetRegistry,
        presets_dir=providers.Callable(lambda cfg: cfg.presets.dir, config),
        strict=providers.Callable(lambda cfg: bool(cfg.presets.strict), config),
    )

    prefect_engine = providers.Singleton(
        PrefectWorkPoolEngine,
        prefect_client=prefect_client,
        work_pool_name=providers.Callable(lambda cfg: cfg.prefect.work_pool_name, config),
        work_pool_type=providers.Callable(lambda cfg: cfg.prefect.work_pool_type, config),
        flow_name=providers.Callable(lambda cfg: cfg.prefect.flow_name, config),
        concurrency_limit=providers.Callable(lambda cfg: int(cfg.prefect.concurrency_limit), config),
        preset_registry=preset_registry,
    )

    execution_engine = providers.Selector(
        providers.Callable(lambda cfg: cfg.execution.engine, config),
        local=local_engine,
        kubeflow=kubeflow_engine,
        prefect=prefect_engine,
    )

    notification_sink = providers.Singleton(
        WebhookNotificationSink,
        endpoint=providers.Callable(lambda cfg: cfg.notification.webhook.endpoint, config),
        timeout_seconds=providers.Callable(lambda cfg: cfg.notification.webhook.timeout_seconds, config),
    )

    label_studio_client = providers.Singleton(
        LabelStudioClient,
        url=providers.Callable(lambda cfg: cfg.label_studio.url, config),
        api_key=providers.Callable(lambda cfg: cfg.label_studio.api_key, config),
    )

    ls_engine = providers.Singleton(
        create_ls_engine,
        database_url=providers.Callable(lambda cfg: cfg.label_studio.database_url, config),
    )
    ls_session_factory = providers.Singleton(
        create_ls_session_factory,
        engine=ls_engine,
    )
    ls_read_repository = providers.Singleton(
        LsReadRepository,
        session_factory=ls_session_factory,
    )

    embedding_service = providers.Singleton(
        EmbeddingClient,
        grpc_target=providers.Callable(lambda cfg: cfg.embedding.grpc_target, config),
    )
    llm_client = providers.Singleton(
        OpenAICompatibleLlmClient,
        base_url=providers.Callable(lambda cfg: cfg.llm.base_url, config),
        api_key=providers.Callable(lambda cfg: cfg.llm.api_key, config),
        model=providers.Callable(lambda cfg: cfg.llm.model, config),
        timeout_seconds=providers.Callable(lambda cfg: float(cfg.llm.timeout_seconds), config),
    )
    inference_worker = providers.Singleton(
        InferenceWorkerClient,
        base_url=providers.Callable(lambda cfg: cfg.inference.base_url, config),
    )
    feature_ops = providers.Singleton(
        FeatureOpsService,
        repository=repository,
        embedding_service=embedding_service,
        inference_worker=inference_worker,
    )
    artifacts = providers.Singleton(ArtifactService, storage=artifact_storage, repository=repository)
    orchestrator = providers.Singleton(
        TrainingOrchestrator,
        engine=execution_engine,
        notification_sink=notification_sink,
        repository=repository,
        artifact_service=artifacts,
    )
    model_service = providers.Singleton(
        ModelService,
        repository=repository,
        artifact_storage=artifact_storage,
    )
    prediction_service = providers.Singleton(
        PredictionService,
        repository=repository,
        artifact_storage=artifact_storage,
        config=config,
        embedding_client=embedding_service,
        llm_client=llm_client,
        inference_worker=inference_worker,
    )
    prediction_orchestrator = providers.Singleton(
        PredictionOrchestrator,
        prefect_client=prefect_client,
        repository=repository,
    )
    service_health = providers.Singleton(
        ServiceHealthService,
        config=config,
        prefect_client=prefect_client,
        embedding_client=embedding_service,
    )
    auth_service: providers.Singleton[AuthService] = providers.Singleton(AuthService)
