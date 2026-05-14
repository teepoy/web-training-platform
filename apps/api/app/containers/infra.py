from __future__ import annotations
# pyright: reportMissingImports=false

from dependency_injector import containers, providers

from app.core.config import load_config
from app.db.ls_session import create_ls_engine, create_ls_session_factory
from app.db.session import create_engine, create_session_factory
from app.repositories.ls_read_repository import LsReadRepository
from app.repositories.sql_repository import SqlRepository
from app.services.embedding import EmbeddingClient
from app.services.inference_worker import InferenceWorkerClient
from app.services.kubeflow_client import KubeflowClient
from app.services.label_studio import LabelStudioClient
from app.services.llm import OpenAICompatibleLlmClient
from app.storage.minio_storage import InMemoryArtifactStorage, MinioArtifactStorage


class InfraContainer(containers.DeclarativeContainer):
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

    label_studio_client = providers.Singleton(
        LabelStudioClient,
        url=providers.Callable(lambda cfg: cfg.label_studio.url, config),
        api_key=providers.Callable(lambda cfg: cfg.label_studio.api_key, config),
    )

    ls_engine = providers.Singleton(
        create_ls_engine,
        database_url=providers.Callable(
            lambda cfg: cfg.label_studio.database_url, config
        ),
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
        timeout_seconds=providers.Callable(
            lambda cfg: float(cfg.llm.timeout_seconds), config
        ),
    )
    inference_worker = providers.Singleton(
        InferenceWorkerClient,
        base_url=providers.Callable(lambda cfg: cfg.inference.base_url, config),
    )
