from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from omegaconf import DictConfig  # pyright: ignore[reportMissingImports]

from app.modules.datasets.application.sample_access.factory import SampleAccessFactory
from app.shared.db.sql_repository import SqlRepository
from app.shared.infrastructure.surface_store import SurfaceStore


def get_config(request: Request) -> DictConfig:
    return request.app.state.container.config


def get_repository(request: Request) -> SqlRepository:
    return SqlRepository(session_factory=request.app.state.container.session_factory)


def get_sample_access_factory(request: Request) -> SampleAccessFactory:
    return request.app.state.container.sample_access_factory


def get_surface_store(request: Request) -> SurfaceStore:
    return request.app.state.container.surface_store


ConfigDep = Annotated[DictConfig, Depends(get_config)]
RepositoryDep = Annotated[SqlRepository, Depends(get_repository)]
SampleAccessFactoryDep = Annotated[
    SampleAccessFactory, Depends(get_sample_access_factory)
]
SurfaceStoreDep = Annotated[SurfaceStore, Depends(get_surface_store)]
