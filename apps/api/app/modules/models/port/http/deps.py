from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from omegaconf import DictConfig

from app.modules.models.app.services.model_service import ModelService
from app.shared.domain.protocols import ArtifactStorage


def get_model_service(request: Request) -> ModelService:
    return request.app.state.app_context.models.model_service


def get_artifact_storage(request: Request) -> ArtifactStorage:
    return request.app.state.app_context.shared.artifact_storage


def get_config(request: Request) -> DictConfig:
    return request.app.state.app_context.shared.config


ModelServiceDep = Annotated[ModelService, Depends(get_model_service)]
