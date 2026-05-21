from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from omegaconf import DictConfig  # pyright: ignore[reportMissingImports]

from app.modules.datasets.application.sample_access.factory import SampleAccessFactory
from app.modules.datasets.application.services.dataset_capability_guard import (
    assert_not_sparse,
)
from app.modules.datasets.application.services.dataset_payload_store import (
    DatasetPayloadStore,
)
from app.modules.datasets.application.services.dataset_service import DatasetService
from app.modules.datasets.domain.repository import DatasetRepository
from app.shared.domain.protocols import ArtifactStorage, LabelStudioClient


def get_repository(request: Request) -> DatasetRepository:
    return request.app.state.container.dataset_repository


def get_sample_access_factory(request: Request) -> SampleAccessFactory:
    return request.app.state.container.sample_access_factory


def get_label_studio_client(request: Request) -> LabelStudioClient:
    return request.app.state.container.label_studio_client


def get_artifact_storage(request: Request) -> ArtifactStorage:
    return request.app.state.container.artifact_storage


def get_dataset_payload_store(request: Request) -> DatasetPayloadStore:
    return request.app.state.container.dataset_payload_store


def get_config(request: Request) -> DictConfig:
    return request.app.state.container.config


def get_dataset_service(
    repository: Annotated[DatasetRepository, Depends(get_repository)],
    sample_factory: Annotated[SampleAccessFactory, Depends(get_sample_access_factory)],
    ls_client: Annotated[LabelStudioClient, Depends(get_label_studio_client)],
    storage: Annotated[ArtifactStorage, Depends(get_artifact_storage)],
    payload_store: Annotated[DatasetPayloadStore, Depends(get_dataset_payload_store)],
    config: Annotated[DictConfig, Depends(get_config)],
) -> DatasetService:
    return DatasetService(
        repository=repository,
        sample_factory=sample_factory,
        ls_client=ls_client,
        storage=storage,
        payload_store=payload_store,
        capability_guard=assert_not_sparse,
        config=config,
    )


DatasetServiceDep = Annotated[DatasetService, Depends(get_dataset_service)]
LabelStudioClientDep = Annotated[LabelStudioClient, Depends(get_label_studio_client)]
