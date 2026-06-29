from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from omegaconf import DictConfig

from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory
from app.modules.datasets.port.local import (
    DatasetService,
    FeatureOpsService,
)
from app.modules.prediction.app.services.batch_lookup import BatchPredictionService
from app.modules.prediction.app.services.prediction_orchestrator import (
    PredictionOrchestrator,
)
from app.modules.prediction.app.services.prediction_service import (
    PredictionService,
)
from app.modules.prediction.domain.repository import PredictionRepository
from app.shared.application.artifacts import ArtifactService
from app.shared.db.sql_repository import SqlRepository
from app.shared.domain.protocols import (
    ArtifactStorage,
    LlmClient,
    PrefectClient,
)
from app.shared.infrastructure.redis.event_publisher import (
    RedisEventPublisher,
)


def get_config(request: Request) -> DictConfig:
    return request.app.state.app_context.shared.config


def get_prediction_repository(request: Request) -> PredictionRepository:
    return request.app.state.app_context.prediction.prediction_repository


def get_sql_repository(request: Request) -> SqlRepository:
    repository = request.app.state.app_context.prediction.prediction_repository
    if not isinstance(repository, SqlRepository):
        raise TypeError("Prediction repository is not a SqlRepository")
    return repository


def get_artifact_storage(request: Request) -> ArtifactStorage:
    return request.app.state.app_context.shared.artifact_storage


def get_llm_client(request: Request) -> LlmClient:
    return request.app.state.app_context.shared.llm_client


def get_prefect_client(request: Request) -> PrefectClient:
    return request.app.state.app_context.shared.prefect_client


def get_dataset_storage_factory(request: Request) -> DatasetStorageFactory:
    return request.app.state.app_context.datasets.dataset_storage_factory


def get_feature_ops_service(
    repository: Annotated[SqlRepository, Depends(get_sql_repository)],
) -> FeatureOpsService:
    return FeatureOpsService(
        repository=repository,
    )


def get_artifact_service(
    storage: Annotated[ArtifactStorage, Depends(get_artifact_storage)],
    repository: Annotated[SqlRepository, Depends(get_sql_repository)],
) -> ArtifactService:
    return ArtifactService(storage=storage, repository=repository)


def get_prediction_service(
    repository: Annotated[PredictionRepository, Depends(get_prediction_repository)],
    artifact_storage: Annotated[ArtifactStorage, Depends(get_artifact_storage)],
    config: Annotated[DictConfig, Depends(get_config)],
    dataset_storage_factory: Annotated[
        DatasetStorageFactory, Depends(get_dataset_storage_factory)
    ],
    llm_client: Annotated[LlmClient, Depends(get_llm_client)],
) -> PredictionService:
    return PredictionService(
        repository=repository,
        artifact_storage=artifact_storage,
        config=config,
        dataset_storage_factory=dataset_storage_factory,
        llm_client=llm_client,
    )


def get_prediction_orchestrator(
    prefect_client: Annotated[PrefectClient, Depends(get_prefect_client)],
    repository: Annotated[PredictionRepository, Depends(get_prediction_repository)],
) -> PredictionOrchestrator:
    return PredictionOrchestrator(
        prefect_client=prefect_client,
        repository=repository,
    )


def get_batch_prediction_service(request: Request) -> BatchPredictionService:
    return request.app.state.app_context.prediction.batch_prediction


def get_dataset_service(request: Request) -> DatasetService:
    return request.app.state.app_context.datasets.dataset_service


def get_redis_event_publisher(request: Request) -> RedisEventPublisher:
    return request.app.state.app_context.shared.redis_event_publisher


RedisEventPublisherDep = Annotated[
    RedisEventPublisher,
    Depends(get_redis_event_publisher),
]

ConfigDep = Annotated[DictConfig, Depends(get_config)]
PredictionRepositoryDep = Annotated[
    PredictionRepository,
    Depends(get_prediction_repository),
]
SqlRepositoryDep = Annotated[SqlRepository, Depends(get_sql_repository)]
ArtifactStorageDep = Annotated[ArtifactStorage, Depends(get_artifact_storage)]
DatasetStorageFactoryDep = Annotated[
    DatasetStorageFactory,
    Depends(get_dataset_storage_factory),
]
FeatureOpsServiceDep = Annotated[
    FeatureOpsService,
    Depends(get_feature_ops_service),
]
ArtifactServiceDep = Annotated[ArtifactService, Depends(get_artifact_service)]
PredictionServiceDep = Annotated[PredictionService, Depends(get_prediction_service)]
PredictionOrchestratorDep = Annotated[
    PredictionOrchestrator,
    Depends(get_prediction_orchestrator),
]
BatchPredictionServiceDep = Annotated[
    BatchPredictionService,
    Depends(get_batch_prediction_service),
]
DatasetServiceDep = Annotated[
    DatasetService,
    Depends(get_dataset_service),
]
