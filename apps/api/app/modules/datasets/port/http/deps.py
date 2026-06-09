from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from omegaconf import DictConfig
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modules.datasets.app.services.dataset_capability_guard import (
    assert_not_sparse,
)
from platform_runtime.sparse import DatasetPayloadStore
from app.modules.datasets.app.services.dataset_service import DatasetService

from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory
from app.modules.datasets.domain.repository import DatasetRepository
from app.shared.domain.protocols import (
    ArtifactStorage,
    LabelStudioClient,
)


def get_repository(request: Request) -> DatasetRepository:
    return request.app.state.app_context.datasets.dataset_repository


def get_dataset_storage_factory(request: Request) -> DatasetStorageFactory:
    return request.app.state.app_context.datasets.dataset_storage_factory


def get_label_studio_client(request: Request) -> LabelStudioClient:
    return request.app.state.app_context.shared.label_studio_client


def get_artifact_storage(request: Request) -> ArtifactStorage:
    return request.app.state.app_context.shared.artifact_storage


def get_dataset_payload_store(request: Request) -> DatasetPayloadStore:
    return request.app.state.app_context.datasets.dataset_payload_store


def get_config(request: Request) -> DictConfig:
    return request.app.state.app_context.shared.config


def get_dataset_service(
    repository: Annotated[DatasetRepository, Depends(get_repository)],
    storage_factory: Annotated[
        DatasetStorageFactory, Depends(get_dataset_storage_factory)
    ],
    ls_client: Annotated[LabelStudioClient, Depends(get_label_studio_client)],
    storage: Annotated[ArtifactStorage, Depends(get_artifact_storage)],
    payload_store: Annotated[DatasetPayloadStore, Depends(get_dataset_payload_store)],
    config: Annotated[DictConfig, Depends(get_config)],
) -> DatasetService:
    return DatasetService(
        repository=repository,
        storage_factory=storage_factory,
        ls_client=ls_client,
        storage=storage,
        payload_store=payload_store,
        capability_guard=assert_not_sparse,
        config=config,
    )


DatasetServiceDep = Annotated[DatasetService, Depends(get_dataset_service)]
LabelStudioClientDep = Annotated[LabelStudioClient, Depends(get_label_studio_client)]


def get_session_factory(request: Request) -> async_sessionmaker:
    return request.app.state.app_context.shared.session_factory


SessionFactoryDep = Annotated[async_sessionmaker, Depends(get_session_factory)]
