from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from omegaconf import DictConfig  # pyright: ignore[reportMissingImports]

from app.modules.models.application.services.model_service import ModelService
from app.shared.domain.protocols import ArtifactStorage


def get_model_service(request: Request) -> ModelService:
    container = request.app.state.container
    return ModelService(
        repository=container.model_repository,
        artifact_storage=container.artifact_storage,
    )


def get_artifact_storage(request: Request) -> ArtifactStorage:
    return request.app.state.container.artifact_storage


def get_config(request: Request) -> DictConfig:
    return request.app.state.container.config


ModelServiceDep = Annotated[ModelService, Depends(get_model_service)]
