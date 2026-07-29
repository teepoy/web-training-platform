from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.modules.training.domain.repository import TrainingRepository
from app.modules.training.port.local import TrainingExecutionPort
from app.shared.injection import resolve


def get_training_orchestrator(request: Request) -> TrainingExecutionPort:
    return resolve(request, TrainingExecutionPort)


def get_repository(request: Request) -> TrainingRepository:
    return resolve(request, TrainingRepository)


TrainingOrchestratorDep = Annotated[
    TrainingExecutionPort,
    Depends(get_training_orchestrator),
]
RepositoryDep = Annotated[TrainingRepository, Depends(get_repository)]
