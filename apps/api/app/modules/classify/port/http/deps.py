from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from omegaconf import DictConfig
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory
from app.shared.db.sql_repository import SqlRepository
from app.shared.infrastructure.surface_store import SurfaceStore


def get_config(request: Request) -> DictConfig:
    return request.app.state.app_context.shared.config


def get_session_factory(request: Request) -> async_sessionmaker:
    return request.app.state.app_context.shared.session_factory


def get_repository(request: Request) -> SqlRepository:
    return SqlRepository(
        session_factory=request.app.state.app_context.shared.session_factory
    )


def get_dataset_storage_factory(request: Request) -> DatasetStorageFactory:
    return request.app.state.app_context.datasets.dataset_storage_factory


def get_surface_store(request: Request) -> SurfaceStore:
    return request.app.state.app_context.shared.surface_store


ConfigDep = Annotated[DictConfig, Depends(get_config)]
SessionFactoryDep = Annotated[async_sessionmaker, Depends(get_session_factory)]
RepositoryDep = Annotated[SqlRepository, Depends(get_repository)]
DatasetStorageFactoryDep = Annotated[
    DatasetStorageFactory, Depends(get_dataset_storage_factory)
]
SurfaceStoreDep = Annotated[SurfaceStore, Depends(get_surface_store)]
