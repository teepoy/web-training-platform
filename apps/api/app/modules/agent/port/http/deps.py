from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.core.config import AppConfig
from app.modules.agent.app.services.session_store import SessionStore
from app.modules.datasets.domain.repository import DatasetRepository
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.modules.models.port.local import ModelCatalogPort
from app.modules.prediction.domain.repository import PredictionRepository
from app.modules.prediction.port.local import PredictionExecutionPort
from app.modules.jobs.schedules.port.local import ScheduleManagementPort
from app.modules.training.port.local import TrainingExecutionPort
from app.modules.training.domain.repository import TrainingRepository
from app.shared.domain.protocols import LabelStudioClient
from app.shared.infrastructure.surface_store import SurfaceStore
from app.shared.injection import resolve


def get_surface_store(request: Request) -> SurfaceStore:
    return resolve(request, SurfaceStore)


def get_session_store(request: Request) -> SessionStore:
    return resolve(request, SessionStore)


def get_label_studio_client(request: Request) -> LabelStudioClient:
    return resolve(request, LabelStudioClient)


def get_config(request: Request) -> AppConfig:
    return resolve(request, AppConfig)


def get_dataset_repository(request: Request) -> DatasetRepository:
    return resolve(request, DatasetRepository)


def get_training_repository(request: Request) -> TrainingRepository:
    return resolve(request, TrainingRepository)


def get_dataset_storage_factory(request: Request) -> DatasetStorageFactoryPort:
    return resolve(request, DatasetStorageFactoryPort)


def get_training_submission(request: Request) -> TrainingExecutionPort:
    return resolve(request, TrainingExecutionPort)


def get_prediction_submission(request: Request) -> PredictionExecutionPort:
    return resolve(request, PredictionExecutionPort)


def get_prediction_repository(request: Request) -> PredictionRepository:
    return resolve(request, PredictionRepository)


def get_scheduler_service(request: Request) -> ScheduleManagementPort:
    return resolve(request, ScheduleManagementPort)


def get_model_service(request: Request) -> ModelCatalogPort:
    return resolve(request, ModelCatalogPort)


SurfaceStoreDep = Annotated[SurfaceStore, Depends(get_surface_store)]
SessionStoreDep = Annotated[SessionStore, Depends(get_session_store)]
LabelStudioClientDep = Annotated[LabelStudioClient, Depends(get_label_studio_client)]
ConfigDep = Annotated[AppConfig, Depends(get_config)]
DatasetRepositoryDep = Annotated[
    DatasetRepository,
    Depends(get_dataset_repository),
]
TrainingRepositoryDep = Annotated[
    TrainingRepository,
    Depends(get_training_repository),
]
DatasetStorageFactoryDep = Annotated[
    DatasetStorageFactoryPort, Depends(get_dataset_storage_factory)
]
TrainingSubmissionDep = Annotated[
    TrainingExecutionPort, Depends(get_training_submission)
]
PredictionSubmissionDep = Annotated[
    PredictionExecutionPort,
    Depends(get_prediction_submission),
]
PredictionRepositoryDep = Annotated[
    PredictionRepository,
    Depends(get_prediction_repository),
]
SchedulerServiceDep = Annotated[ScheduleManagementPort, Depends(get_scheduler_service)]
ModelServiceDep = Annotated[ModelCatalogPort, Depends(get_model_service)]
