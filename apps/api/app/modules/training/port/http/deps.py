from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.modules.training.app.services.orchestrator import TrainingOrchestrator
from app.shared.db.sql_repository import SqlRepository


def get_training_orchestrator(request: Request) -> TrainingOrchestrator:
    return request.app.state.app_context.training.training_orchestrator


def get_repository(request: Request) -> SqlRepository:
    return request.app.state.app_context.training.repository


TrainingOrchestratorDep = Annotated[
    TrainingOrchestrator,
    Depends(get_training_orchestrator),
]
RepositoryDep = Annotated[SqlRepository, Depends(get_repository)]
