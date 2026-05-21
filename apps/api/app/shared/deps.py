from __future__ import annotations

from unittest.mock import Mock
from typing import Any

from fastapi import Depends, Request
from omegaconf import DictConfig  # pyright: ignore[reportMissingImports]

from app.shared.domain.protocols import (
    ArtifactStorage,
    EmbeddingClient,
    LabelStudioClient,
    PrefectClient,
)
from app.shared.api.schemas import DatasetType, TaskType
from app.modules.dashboard.application.services.service_health import (
    ServiceHealthService,
)
from app.modules.datasets.application.sample_access.factory import SampleAccessFactory
from app.modules.datasets.application.services.feature_ops import FeatureOpsService
from app.modules.models.application.services.model_service import ModelService
from app.modules.prediction.application.services.prediction_orchestrator import (
    PredictionOrchestrator,
)
from app.modules.prediction.application.services.prediction_service import (
    PredictionService,
)
from app.modules.presets.registry import PresetRegistry
from app.modules.preview.application.services.preview_service import PreviewService
from app.modules.schedules.application.services.scheduler import SchedulerService
from app.modules.sensors.application.services.sensor_dispatch import (
    SensorDispatchService,
)
from app.modules.sensors.domain.entities.registry import SensorRegistry
from app.modules.sensors.infrastructure.repositories.repository import SensorRepository
from app.modules.task_tracker.application.services.task_tracker import (
    TaskTrackerService,
)
from app.modules.training.application.services.orchestrator import TrainingOrchestrator
from app.shared.application.artifacts import ArtifactService
from app.shared.db.sql_repository import SqlRepository
from app.shared.infrastructure.label_studio.read_repository import LsReadRepository
from app.shared.infrastructure.label_studio.session import (
    create_ls_engine,
    create_ls_session_factory,
)
from app.shared.infrastructure.surface_store import SurfaceStore
from app.modules.agent.application.services.session_store import SessionStore
from app.modules.auth.interfaces.controllers.deps import (  # noqa: F401
    _get_session_factory,
    get_current_org,
    get_current_user,
)


def get_container(request: Request) -> Any:
    return request.app.state.container


def _provider_value(provider: Any) -> Any:
    if isinstance(provider, Mock):
        return provider()
    return provider()


def get_repository(c: Any = Depends(get_container)) -> SqlRepository:
    return c.prediction_repository


def get_artifact_storage(c: Any = Depends(get_container)) -> ArtifactStorage:
    return c.artifact_storage


def get_label_studio_client(c: Any = Depends(get_container)) -> LabelStudioClient:
    return c.label_studio_client


def get_ls_read_repository(c: Any = Depends(get_container)) -> LsReadRepository:
    engine = create_ls_engine(database_url=str(c.config.label_studio.database_url))
    return LsReadRepository(session_factory=create_ls_session_factory(engine=engine))


def get_sample_access_factory(c: Any = Depends(get_container)) -> SampleAccessFactory:
    return c.sample_access_factory


def get_task_tracker(c: Any = Depends(get_container)) -> TaskTrackerService:
    return TaskTrackerService(
        repository=c.task_tracker_repository,
        prefect_client=c.prefect_client,
        config=c.config,
    )


def get_model_service(c: Any = Depends(get_container)) -> ModelService:
    return c.model_service


def get_sensor_repository(c: Any = Depends(get_container)) -> SensorRepository:
    return c.sensor_repository


def get_sensor_dispatch(c: Any = Depends(get_container)) -> SensorDispatchService:
    return SensorDispatchService(
        repository=c.sensor_repository, prefect_client=c.prefect_client
    )


def get_sensor_dispatch_service(
    c: Any = Depends(get_container),
) -> SensorDispatchService:
    return SensorDispatchService(
        repository=c.sensor_repository, prefect_client=c.prefect_client
    )


def get_sensor_registry(c: Any = Depends(get_container)) -> SensorRegistry:
    return c.sensor_registry


def get_orchestrator(c: Any = Depends(get_container)) -> TrainingOrchestrator:
    return c.training_orchestrator


def get_prediction_service(c: Any = Depends(get_container)) -> PredictionService:
    return PredictionService(
        repository=c.prediction_repository,
        artifact_storage=c.artifact_storage,
        config=c.config,
        embedding_client=c.embedding_client,
        llm_client=c.llm_client,
        inference_worker=c.inference_worker,
        gpu_worker=c.gpu_worker,
    )


def get_prediction_orchestrator(
    c: Any = Depends(get_container),
) -> PredictionOrchestrator:
    return c.prediction_orchestrator


def get_scheduler_service(c: Any = Depends(get_container)) -> SchedulerService:
    return c.scheduler_service


def get_preview_service(c: Any = Depends(get_container)) -> PreviewService:
    return PreviewService(store=c.preview_store, upstream=c.preview_upstream)


def get_surface_store(c: Any = Depends(get_container)) -> SurfaceStore:
    return c.surface_store


def get_session_store(c: Any = Depends(get_container)) -> SessionStore:
    return c.session_store


def get_preset_registry(c: Any = Depends(get_container)) -> PresetRegistry:
    return c.preset_registry


def get_embedding_service(c: Any = Depends(get_container)) -> EmbeddingClient:
    return c.embedding_client


def get_config(c: Any = Depends(get_container)) -> DictConfig:
    return c.config


def get_feature_ops(c: Any = Depends(get_container)) -> FeatureOpsService:
    return FeatureOpsService(
        repository=c.prediction_repository,
        embedding_service=c.embedding_client,
        inference_worker=c.inference_worker,
        gpu_worker=c.gpu_worker,
    )


def get_artifacts(c: Any = Depends(get_container)) -> ArtifactService:
    return ArtifactService(
        storage=c.artifact_storage, repository=c.prediction_repository
    )


def get_service_health(c: Any = Depends(get_container)) -> ServiceHealthService:
    return c.service_health_service


def get_prefect_client(c: Any = Depends(get_container)) -> PrefectClient:
    return c.prefect_client


def _infer_dataset_type(task_type: TaskType) -> DatasetType:
    if task_type == TaskType.VQA:
        return DatasetType.IMAGE_VQA
    return DatasetType.IMAGE_CLASSIFICATION


def _make_ls_image_url(uri: str) -> str:
    """Convert platform image URI to LS-accessible URL."""
    from urllib.parse import quote

    if uri.startswith(("s3://", "memory://")):
        return f"/api/v1/images/resolve?uri={quote(uri, safe='')}"
    return uri
