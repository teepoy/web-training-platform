from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.modules.datasets.port.dataset_reader import DatasetReader
from app.modules.datasets.port.local import IDatasetService
from app.modules.prediction.domain.repository import PredictionRepository
from app.shared.application.artifacts import ArtifactService
from app.shared.domain.protocols import ArtifactStorage
from app.shared.context import SharedInfra
from app.shared.infrastructure.redis.event_publisher import (
    RedisEventPublisher,
)
from app.modules.prediction.port.local import (
    PredictionCollectionPort,
    PredictionExecutionPort,
    PredictionQueryPort,
    PredictionReviewPort,
    PredictionRuntimePort,
)
from app.shared.injection import resolve


def get_prediction_repository(request: Request) -> PredictionRepository:
    return resolve(request, PredictionRepository)


def get_dataset_reader(request: Request) -> DatasetReader:
    return resolve(request, DatasetReader)


def get_artifact_storage(request: Request) -> ArtifactStorage:
    return resolve(request, ArtifactStorage)


def get_artifact_service(
    storage: Annotated[ArtifactStorage, Depends(get_artifact_storage)],
) -> ArtifactService:
    return ArtifactService(storage=storage)


def get_prediction_runtime(request: Request) -> PredictionRuntimePort:
    return resolve(request, PredictionRuntimePort)


def get_prediction_query(request: Request) -> PredictionQueryPort:
    return resolve(request, PredictionQueryPort)


def get_prediction_collection(request: Request) -> PredictionCollectionPort:
    return resolve(request, PredictionCollectionPort)


def get_prediction_review(request: Request) -> PredictionReviewPort:
    return resolve(request, PredictionReviewPort)


def get_prediction_orchestrator(request: Request) -> PredictionExecutionPort:
    return resolve(request, PredictionExecutionPort)


def get_dataset_service(request: Request) -> IDatasetService:
    return resolve(request, IDatasetService)


def get_redis_event_publisher(request: Request) -> RedisEventPublisher:
    publisher = resolve(request, SharedInfra).redis_event_publisher
    if not isinstance(publisher, RedisEventPublisher):
        raise RuntimeError("Redis event publisher is not initialized")
    return publisher


RedisEventPublisherDep = Annotated[
    RedisEventPublisher,
    Depends(get_redis_event_publisher),
]

PredictionRepositoryDep = Annotated[
    PredictionRepository,
    Depends(get_prediction_repository),
]
DatasetReaderDep = Annotated[DatasetReader, Depends(get_dataset_reader)]
ArtifactServiceDep = Annotated[ArtifactService, Depends(get_artifact_service)]
PredictionRuntimeDep = Annotated[
    PredictionRuntimePort,
    Depends(get_prediction_runtime),
]
PredictionQueryDep = Annotated[
    PredictionQueryPort,
    Depends(get_prediction_query),
]
PredictionCollectionDep = Annotated[
    PredictionCollectionPort,
    Depends(get_prediction_collection),
]
PredictionReviewDep = Annotated[
    PredictionReviewPort,
    Depends(get_prediction_review),
]
PredictionOrchestratorDep = Annotated[
    PredictionExecutionPort, Depends(get_prediction_orchestrator)
]
DatasetServiceDep = Annotated[
    IDatasetService,
    Depends(get_dataset_service),
]
