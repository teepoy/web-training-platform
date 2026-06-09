from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from omegaconf import DictConfig
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modules.agent.app.services.session_store import SessionStore
from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory
from app.modules.models.app.services.model_service import ModelService
from app.modules.prediction.app.services.prediction_orchestrator import (
    PredictionOrchestrator,
)
from app.modules.schedules.app.services.scheduler import SchedulerService
from app.modules.training.app.services.orchestrator import TrainingOrchestrator
from app.shared.db.sql_repository import SqlRepository
from app.shared.domain.protocols import LabelStudioClient
from app.shared.infrastructure.surface_store import SurfaceStore


def get_surface_store(request: Request) -> SurfaceStore:
    return request.app.state.app_context.shared.surface_store


def get_session_store(request: Request) -> SessionStore:
    return request.app.state.app_context.agent.session_store


def get_label_studio_client(request: Request) -> LabelStudioClient:
    return request.app.state.app_context.shared.label_studio_client


def get_config(request: Request) -> DictConfig:
    return request.app.state.app_context.shared.config


def get_session_factory(request: Request) -> async_sessionmaker:
    return request.app.state.app_context.shared.session_factory


def get_repository(request: Request) -> SqlRepository:
    return SqlRepository(
        session_factory=request.app.state.app_context.shared.session_factory
    )


def get_dataset_storage_factory(request: Request) -> DatasetStorageFactory:
    return request.app.state.app_context.datasets.dataset_storage_factory


def get_orchestrator(request: Request) -> TrainingOrchestrator:
    return request.app.state.app_context.training.training_orchestrator


def get_prediction_orchestrator(request: Request) -> PredictionOrchestrator:
    return request.app.state.app_context.prediction.prediction_orchestrator


def get_scheduler_service(request: Request) -> SchedulerService:
    return request.app.state.app_context.schedules.scheduler_service


def get_model_service(request: Request) -> ModelService:
    return request.app.state.app_context.models.model_service


SurfaceStoreDep = Annotated[SurfaceStore, Depends(get_surface_store)]
SessionStoreDep = Annotated[SessionStore, Depends(get_session_store)]
LabelStudioClientDep = Annotated[LabelStudioClient, Depends(get_label_studio_client)]
ConfigDep = Annotated[DictConfig, Depends(get_config)]
SessionFactoryDep = Annotated[async_sessionmaker, Depends(get_session_factory)]
RepositoryDep = Annotated[SqlRepository, Depends(get_repository)]
DatasetStorageFactoryDep = Annotated[
    DatasetStorageFactory, Depends(get_dataset_storage_factory)
]
TrainingOrchestratorDep = Annotated[TrainingOrchestrator, Depends(get_orchestrator)]
PredictionOrchestratorDep = Annotated[
    PredictionOrchestrator,
    Depends(get_prediction_orchestrator),
]
SchedulerServiceDep = Annotated[SchedulerService, Depends(get_scheduler_service)]
ModelServiceDep = Annotated[ModelService, Depends(get_model_service)]
