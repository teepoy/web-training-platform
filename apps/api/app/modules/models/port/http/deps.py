from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.core.config import AppConfig
from app.modules.models.port.local import ModelManagementPort
from app.shared.domain.protocols import ArtifactStorage
from app.shared.injection import resolve


def get_model_service(request: Request) -> ModelManagementPort:
    return resolve(request, ModelManagementPort)


def get_artifact_storage(request: Request) -> ArtifactStorage:
    return resolve(request, ArtifactStorage)


def get_config(request: Request) -> AppConfig:
    return resolve(request, AppConfig)


ModelServiceDep = Annotated[ModelManagementPort, Depends(get_model_service)]
