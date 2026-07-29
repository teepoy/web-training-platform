from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.core.config import AppConfig
from app.modules.datasets.domain.repository import DatasetRepository
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.shared.infrastructure.surface_store import SurfaceStore
from app.shared.injection import resolve


def get_config(request: Request) -> AppConfig:
    return resolve(request, AppConfig)


def get_repository(request: Request) -> DatasetRepository:
    return resolve(request, DatasetRepository)


def get_dataset_storage_factory(request: Request) -> DatasetStorageFactoryPort:
    return resolve(request, DatasetStorageFactoryPort)


def get_surface_store(request: Request) -> SurfaceStore:
    return resolve(request, SurfaceStore)


ConfigDep = Annotated[AppConfig, Depends(get_config)]
RepositoryDep = Annotated[DatasetRepository, Depends(get_repository)]
DatasetStorageFactoryDep = Annotated[
    DatasetStorageFactoryPort, Depends(get_dataset_storage_factory)
]
SurfaceStoreDep = Annotated[SurfaceStore, Depends(get_surface_store)]
