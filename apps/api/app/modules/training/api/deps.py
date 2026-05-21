from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.modules.datasets.application.sample_access.factory import SampleAccessFactory
from app.modules.training.application.services.orchestrator import TrainingOrchestrator
from app.shared.db.sql_repository import SqlRepository


def get_training_orchestrator(request: Request) -> TrainingOrchestrator:
    return request.app.state.container.training_orchestrator


def get_repository(request: Request) -> SqlRepository:
    repository = request.app.state.container.prediction_repository
    if not isinstance(repository, SqlRepository):
        raise TypeError("Training repository is not a SqlRepository")
    return repository


def get_sample_access_factory(request: Request) -> SampleAccessFactory:
    return request.app.state.container.sample_access_factory


TrainingOrchestratorDep = Annotated[
    TrainingOrchestrator,
    Depends(get_training_orchestrator),
]
RepositoryDep = Annotated[SqlRepository, Depends(get_repository)]
SampleAccessFactoryDep = Annotated[
    SampleAccessFactory,
    Depends(get_sample_access_factory),
]
