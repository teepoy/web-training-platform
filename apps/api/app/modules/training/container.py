from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.modules.training.adapter.clients.kubeflow_client import KubeflowClient
from app.modules.training.adapter.engines.local_kubeflow import (
    KubeflowTrainingOperatorEngine,
    LocalProcessEngine,
)
from app.modules.training.adapter.engines.prefect_engine import (
    PrefectWorkPoolEngine,
)
from app.modules.training.app.services.orchestrator import TrainingOrchestrator
from app.shared.application.artifacts import ArtifactService
from app.shared.context import SharedInfra
from app.shared.db.sql_repository import SqlRepository


@dataclass
class TrainingContext:
    """Training module context — internal implementation, not exposed to other modules."""

    training_orchestrator: TrainingOrchestrator
    repository: SqlRepository
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


def init_training(
    shared: SharedInfra,
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
    repository = SqlRepository(session_factory=shared.session_factory)
    artifact_service = ArtifactService(
        storage=shared.artifact_storage,
        repository=repository,
    )
    orchestrator = TrainingOrchestrator(
        engine=engine,
        notification_sink=shared.notification_sink,
        repository=repository,
        artifact_service=artifact_service,
    )
    return TrainingContext(
        training_orchestrator=orchestrator,
        repository=repository,
        kubeflow_client=kube_client,
        training_engine=engine,
    )
