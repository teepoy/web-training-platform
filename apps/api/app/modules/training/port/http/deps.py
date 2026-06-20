from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.modules.training.app.services.orchestrator import TrainingOrchestrator
from app.shared.domain.protocols import PrefectClient
from app.shared.db.sql_repository import SqlRepository


def get_training_orchestrator(request: Request) -> TrainingOrchestrator:
    return request.app.state.app_context.training.training_orchestrator


def get_repository(request: Request) -> SqlRepository:
    return request.app.state.app_context.training.repository


def get_prefect_client(request: Request) -> PrefectClient:
    return request.app.state.app_context.shared.prefect_client


TrainingOrchestratorDep = Annotated[
    TrainingOrchestrator,
    Depends(get_training_orchestrator),
]
RepositoryDep = Annotated[SqlRepository, Depends(get_repository)]
PrefectClientDep = Annotated[PrefectClient, Depends(get_prefect_client)]
