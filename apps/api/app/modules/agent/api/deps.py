from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from omegaconf import DictConfig  # pyright: ignore[reportMissingImports]

from app.modules.agent.application.services.session_store import SessionStore
from app.modules.models.application.services.model_service import ModelService
from app.modules.prediction.application.services.prediction_orchestrator import (
    PredictionOrchestrator,
)
from app.modules.schedules.application.services.scheduler import SchedulerService
from app.modules.training.application.services.orchestrator import TrainingOrchestrator
from app.shared.db.sql_repository import SqlRepository
from app.shared.domain.protocols import LabelStudioClient
from app.shared.infrastructure.surface_store import SurfaceStore


def get_surface_store(request: Request) -> SurfaceStore:
    return request.app.state.container.surface_store


def get_session_store(request: Request) -> SessionStore:
    return request.app.state.container.session_store


def get_label_studio_client(request: Request) -> LabelStudioClient:
    state_client = request.app.state.container.label_studio_client
    from app.main import container

    legacy_client = container.label_studio_client()
    if legacy_client is not state_client:
        return legacy_client
    return state_client


def get_config(request: Request) -> DictConfig:
    return request.app.state.container.config


def get_repository(request: Request) -> SqlRepository:
    return SqlRepository(session_factory=request.app.state.container.session_factory)


def get_orchestrator(request: Request) -> TrainingOrchestrator:
    return request.app.state.container.training_orchestrator


def get_prediction_orchestrator(request: Request) -> PredictionOrchestrator:
    return request.app.state.container.prediction_orchestrator


def get_scheduler_service(request: Request) -> SchedulerService:
    return request.app.state.container.scheduler_service


def get_model_service(request: Request) -> ModelService:
    return request.app.state.container.model_service


SurfaceStoreDep = Annotated[SurfaceStore, Depends(get_surface_store)]
SessionStoreDep = Annotated[SessionStore, Depends(get_session_store)]
LabelStudioClientDep = Annotated[LabelStudioClient, Depends(get_label_studio_client)]
ConfigDep = Annotated[DictConfig, Depends(get_config)]
RepositoryDep = Annotated[SqlRepository, Depends(get_repository)]
TrainingOrchestratorDep = Annotated[TrainingOrchestrator, Depends(get_orchestrator)]
PredictionOrchestratorDep = Annotated[
    PredictionOrchestrator,
    Depends(get_prediction_orchestrator),
]
SchedulerServiceDep = Annotated[SchedulerService, Depends(get_scheduler_service)]
ModelServiceDep = Annotated[ModelService, Depends(get_model_service)]
