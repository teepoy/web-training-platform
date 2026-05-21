from __future__ import annotations

from unittest.mock import Mock
from typing import Any

from fastapi import Depends
from omegaconf import DictConfig  # pyright: ignore[reportMissingImports]

from app.shared.domain.protocols import (
    ArtifactStorage,
    EmbeddingClient,
    LabelStudioClient,
    PrefectClient,
)
from app.shared.api.schemas import Dataset
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
from app.shared.infrastructure.surface_store import SurfaceStore
from app.modules.agent.application.services.session_store import SessionStore
from app.modules.auth.interfaces.controllers.deps import (  # noqa: F401
    _get_session_factory,
    get_current_org,
    get_current_user,
)


def get_container() -> Any:
    from app.main import container

    return container


def _provider_value(provider: Any) -> Any:
    if isinstance(provider, Mock):
        return provider()
    return provider()


def get_repository(c: Any = Depends(get_container)) -> SqlRepository:
    return _provider_value(c.repository)


def get_artifact_storage(c: Any = Depends(get_container)) -> ArtifactStorage:
    return _provider_value(c.artifact_storage)


def get_label_studio_client(c: Any = Depends(get_container)) -> LabelStudioClient:
    return _provider_value(c.label_studio_client)


def get_ls_read_repository(c: Any = Depends(get_container)) -> LsReadRepository:
    return _provider_value(c.ls_read_repository)


def get_sample_access_factory(c: Any = Depends(get_container)) -> SampleAccessFactory:
    return _provider_value(c.sample_access_factory)


def get_task_tracker(c: Any = Depends(get_container)) -> TaskTrackerService:
    return _provider_value(c.task_tracker)


def get_model_service(c: Any = Depends(get_container)) -> ModelService:
    return _provider_value(c.model_service)


def get_sensor_repository(c: Any = Depends(get_container)) -> SensorRepository:
    return _provider_value(c.sensor_repository)


def get_sensor_dispatch(c: Any = Depends(get_container)) -> SensorDispatchService:
    return _provider_value(c.sensor_dispatch)


def get_sensor_dispatch_service(
    c: Any = Depends(get_container),
) -> SensorDispatchService:
    return _provider_value(c.sensor_dispatch)


def get_sensor_registry(c: Any = Depends(get_container)) -> SensorRegistry:
    return _provider_value(c.sensor_registry)


def get_orchestrator(c: Any = Depends(get_container)) -> TrainingOrchestrator:
    return _provider_value(c.orchestrator)


def get_prediction_service(c: Any = Depends(get_container)) -> PredictionService:
    return _provider_value(c.prediction_service)


def get_prediction_orchestrator(
    c: Any = Depends(get_container),
) -> PredictionOrchestrator:
    return _provider_value(c.prediction_orchestrator)


def get_scheduler_service(c: Any = Depends(get_container)) -> SchedulerService:
    prefect_client = _provider_value(c.prefect_client)
    return SchedulerService(
        prefect_client=prefect_client, repository=_provider_value(c.repository)
    )


def get_preview_service(c: Any = Depends(get_container)) -> PreviewService:
    return _provider_value(c.preview_service)


def get_surface_store(c: Any = Depends(get_container)) -> SurfaceStore:
    return _provider_value(c.surface_store)


def get_session_store(c: Any = Depends(get_container)) -> SessionStore:
    return _provider_value(c.session_store)


def get_preset_registry(c: Any = Depends(get_container)) -> PresetRegistry:
    return _provider_value(c.preset_registry)


def get_embedding_service(c: Any = Depends(get_container)) -> EmbeddingClient:
    return _provider_value(c.embedding_service)


def get_config(c: Any = Depends(get_container)) -> DictConfig:
    return _provider_value(c.config)


def get_feature_ops(c: Any = Depends(get_container)) -> FeatureOpsService:
    return _provider_value(c.feature_ops)


def get_artifacts(c: Any = Depends(get_container)) -> ArtifactService:
    return _provider_value(c.artifacts)


def get_service_health(c: Any = Depends(get_container)) -> ServiceHealthService:
    return _provider_value(c.service_health)


def get_prefect_client(c: Any = Depends(get_container)) -> PrefectClient:
    return _provider_value(c.prefect_client)


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


def _with_ls_url(dataset: Dataset) -> Dataset:
    """Compute ls_project_url and capabilities at response time."""
    from app.shared.api.schemas import SPARSE_NO_LS

    c = get_container()
    access = c.sample_access_factory().create(dataset.storage_mode)
    dataset = dataset.model_copy(update={"capabilities": access.capabilities()})

    if dataset.ls_project_id == SPARSE_NO_LS:
        return dataset
    cfg = c.config()
    ls_url = str(cfg.label_studio.external_url or cfg.label_studio.url).rstrip("/")
    if dataset.ls_project_id and ls_url:
        return dataset.model_copy(
            update={"ls_project_url": f"{ls_url}/projects/{dataset.ls_project_id}"}
        )
    return dataset
