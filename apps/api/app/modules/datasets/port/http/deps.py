from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.core.config import AppConfig
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.modules.datasets.domain.repository import (
    ArtifactLookupRepository,
    DatasetRepository,
)
from app.modules.datasets.port.local import (
    DatasetDeletionGuardPort,
    DatasetRevisionReaderPort,
    IDatasetService,
    SampleSimilarityPort,
)
from app.shared.context import SharedInfra
from app.shared.db.session import AppDatabaseSessionFactory
from app.shared.domain.protocols import (
    ArtifactStorage,
    LabelStudioClient,
)
from app.shared.infrastructure.redis.event_publisher import (
    RedisEventPublisher,
)
from app.shared.injection import resolve
from app.modules.storage.domain.sparse import DatasetPayloadStore


def get_repository(request: Request) -> DatasetRepository:
    return resolve(request, DatasetRepository)


def get_artifact_lookup_repository(request: Request) -> ArtifactLookupRepository:
    return resolve(request, ArtifactLookupRepository)


def get_dataset_storage_factory(request: Request) -> DatasetStorageFactoryPort:
    return resolve(request, DatasetStorageFactoryPort)


def get_label_studio_client(request: Request) -> LabelStudioClient:
    return resolve(request, LabelStudioClient)


def get_artifact_storage(request: Request) -> ArtifactStorage:
    return resolve(request, ArtifactStorage)


def get_dataset_payload_store(request: Request) -> DatasetPayloadStore:
    return resolve(request, DatasetPayloadStore)


def get_config(request: Request) -> AppConfig:
    return resolve(request, AppConfig)


def get_dataset_service(request: Request) -> IDatasetService:
    return resolve(request, IDatasetService)


def get_sample_similarity(request: Request) -> SampleSimilarityPort:
    return resolve(request, SampleSimilarityPort)


def get_dataset_deletion_guard(request: Request) -> DatasetDeletionGuardPort:
    return resolve(request, DatasetDeletionGuardPort)


def get_dataset_revision_reader(request: Request) -> DatasetRevisionReaderPort:
    return resolve(request, DatasetRevisionReaderPort)


DatasetServiceDep = Annotated[IDatasetService, Depends(get_dataset_service)]
DatasetDeletionGuardDep = Annotated[
    DatasetDeletionGuardPort, Depends(get_dataset_deletion_guard)
]
DatasetRevisionReaderDep = Annotated[
    DatasetRevisionReaderPort, Depends(get_dataset_revision_reader)
]
LabelStudioClientDep = Annotated[LabelStudioClient, Depends(get_label_studio_client)]
SampleSimilarityDep = Annotated[SampleSimilarityPort, Depends(get_sample_similarity)]
ArtifactLookupRepositoryDep = Annotated[
    ArtifactLookupRepository, Depends(get_artifact_lookup_repository)
]


def get_redis_event_publisher(request: Request) -> RedisEventPublisher:
    publisher = resolve(request, SharedInfra).redis_event_publisher
    if not isinstance(publisher, RedisEventPublisher):
        raise RuntimeError("Redis event publisher is not initialized")
    return publisher


RedisEventPublisherDep = Annotated[
    RedisEventPublisher, Depends(get_redis_event_publisher)
]


def get_session_factory(request: Request) -> AppDatabaseSessionFactory:
    return resolve(request, AppDatabaseSessionFactory)


SessionFactoryDep = Annotated[AppDatabaseSessionFactory, Depends(get_session_factory)]
