from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from injector import Module, inject, provider, singleton

from app.modules.training.adapter.clients.kubeflow_client import KubeflowClient
from app.modules.dataset_collections.port.local import (
    DatasetCollectionRevisionReaderPort,
)
from app.modules.training.adapter.engines.kubeflow_engine import (
    KubeflowTrainingOperatorEngine,
)
from app.modules.training.adapter.engines.registry import (
    build_registered_training_engine,
)
from app.modules.training.adapter.engines.prefect_engine import (
    PrefectWorkPoolEngine,
)
from app.modules.training.adapter.repositories.repository import TrainingJobRepository
from app.modules.training.app.services.submission_service import (
    TrainingSubmissionService,
)
from app.modules.training.app.services.readiness import TrainingReadinessService
from app.modules.training.app.services.preflight import TrainingPreflightService
from app.modules.training.app.services.status_reconciler import (
    TrainingStatusReconciler,
)
from app.modules.training.domain.repository import TrainingRepository
from app.modules.training.port.local import (
    TrainingDatasetUsagePort,
    TrainingExecutionPort,
    TrainingReadinessPort,
)
from app.modules.datasets.port.dataset_reader import DatasetReader
from app.modules.datasets.port.local import DatasetRevisionReaderPort
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.shared.application.artifacts import ArtifactService
from app.shared.context import SharedInfra
from app.shared.domain.protocols import (
    ArtifactStorage as ArtifactStoragePort,
    TrainingExecutionEngine,
)


@dataclass
class TrainingContext:
    """Training module context — internal implementation, not exposed to other modules."""

    training_submission: TrainingSubmissionService
    training_readiness: TrainingReadinessService
    status_reconciler: TrainingStatusReconciler
    repository: TrainingRepository
    # Internal implementation details (not exposed to other modules)
    kubeflow_client: KubeflowClient | None
    training_engine: Any  # TrainingExecutionEngine


def _build_kubeflow_client(cfg: Any) -> KubeflowClient:
    """Build a KubeflowClient from config.

    Mirrors composition.py:_build_kubeflow_client inline — kept here so the
    training module owns its own wiring.
    """
    return KubeflowClient(
        namespace=str(cfg.k8s.namespace),
        group=str(cfg.kubeflow.group),
        version=str(cfg.kubeflow.version),
        plural=str(cfg.kubeflow.plural),
        in_cluster=bool(cfg.k8s.incluster),
        kubeconfig=str(cfg.k8s.kubeconfig),
    )


def _build_training_engine(
    cfg: Any,
    artifact_storage: Any,
    prefect_client: Any,
    kubeflow_client: KubeflowClient | None,
) -> Any:
    """Build the execution engine from config.

    Mirrors composition.py:_build_training_engine inline — kept here so the
    training module owns its own wiring.
    """
    engine = str(cfg.execution.engine)
    if engine == "local":
        return build_registered_training_engine(engine, artifact_storage)
    if engine == "kubeflow":
        return KubeflowTrainingOperatorEngine(
            kubeflow_client=kubeflow_client,
            image=str(cfg.kubeflow.image),
            storage=artifact_storage,
        )
    if engine == "prefect":
        return PrefectWorkPoolEngine(prefect_client=prefect_client)
    raise RuntimeError(f"Unsupported execution.engine: {engine}")


def init_training(
    shared: SharedInfra,
    dataset_reader: DatasetReader,
    storage_factory: DatasetStorageFactoryPort,
    collection_revisions: DatasetCollectionRevisionReaderPort,
    dataset_revisions: DatasetRevisionReaderPort,
) -> TrainingContext:
    kube_client = (
        _build_kubeflow_client(shared.config)
        if str(shared.config.execution.engine) == "kubeflow"
        else None
    )
    engine = _build_training_engine(
        cfg=shared.config,
        artifact_storage=shared.artifact_storage,
        prefect_client=shared.prefect_client,
        kubeflow_client=kube_client,
    )
    repository = TrainingJobRepository(
        session_factory=shared.session_factory.sessionmaker
    )
    artifact_service = ArtifactService(
        storage=shared.artifact_storage,
        repository=repository,
    )
    readiness = TrainingReadinessService(
        storage_factory=storage_factory,
        artifact_storage=shared.artifact_storage,
    )
    status_reconciler = TrainingStatusReconciler(
        engine=engine,
        repository=repository,
        notification_sink=shared.notification_sink,
        interval_seconds=float(
            shared.config.execution.status_reconcile_interval_seconds
        ),
    )
    submission = TrainingSubmissionService(
        engine=engine,
        notification_sink=shared.notification_sink,
        repository=repository,
        artifact_service=artifact_service,
        dataset_reader=dataset_reader,
        prefect_client=shared.prefect_client,
        collection_revisions=collection_revisions,
        dataset_revisions=dataset_revisions,
        status_reconciler=status_reconciler,
    )
    return TrainingContext(
        training_submission=submission,
        training_readiness=readiness,
        status_reconciler=status_reconciler,
        repository=repository,
        kubeflow_client=kube_client,
        training_engine=engine,
    )


class TrainingModule(Module):
    @inject
    @provider
    @singleton
    def provide_training_context(
        self,
        shared: SharedInfra,
        dataset_reader: DatasetReader,
        storage_factory: DatasetStorageFactoryPort,
        collection_revisions: DatasetCollectionRevisionReaderPort,
        dataset_revisions: DatasetRevisionReaderPort,
    ) -> TrainingContext:
        return init_training(
            shared,
            dataset_reader=dataset_reader,
            storage_factory=storage_factory,
            collection_revisions=collection_revisions,
            dataset_revisions=dataset_revisions,
        )

    @provider
    @singleton
    def provide_training_submission(
        self, context: TrainingContext
    ) -> TrainingSubmissionService:
        return context.training_submission

    @provider
    @singleton
    def provide_training_status_reconciler(
        self,
        context: TrainingContext,
    ) -> TrainingStatusReconciler:
        return context.status_reconciler

    @provider
    @singleton
    def provide_training_execution(
        self, submission: TrainingSubmissionService
    ) -> TrainingExecutionPort:
        return submission

    @provider
    @singleton
    def provide_training_readiness_service(
        self,
        context: TrainingContext,
    ) -> TrainingReadinessService:
        return context.training_readiness

    @provider
    @singleton
    def provide_training_readiness(
        self,
        service: TrainingReadinessService,
    ) -> TrainingReadinessPort:
        return service

    @provider
    @singleton
    def provide_training_preflight(
        self,
        dataset_reader: DatasetReader,
        readiness: TrainingReadinessService,
        collection_revisions: DatasetCollectionRevisionReaderPort,
    ) -> TrainingPreflightService:
        return TrainingPreflightService(
            dataset_reader=dataset_reader,
            readiness=readiness,
            collection_revisions=collection_revisions,
        )

    @provider
    @singleton
    def provide_training_repository(
        self, context: TrainingContext
    ) -> TrainingRepository:
        return context.repository

    @provider
    @singleton
    def provide_training_dataset_usage(
        self, context: TrainingContext
    ) -> TrainingDatasetUsagePort:
        return context.repository

    @provider
    @singleton
    def provide_training_engine(
        self, context: TrainingContext
    ) -> TrainingExecutionEngine:
        return cast(TrainingExecutionEngine, context.training_engine)

    @provider
    @singleton
    def provide_artifact_service(
        self,
        artifact_storage: ArtifactStoragePort,
        repository: TrainingRepository,
    ) -> ArtifactService:
        return ArtifactService(
            storage=artifact_storage,
            repository=repository,
        )
