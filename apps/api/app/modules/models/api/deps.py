from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.modules.models.application.services.model_service import ModelService


def get_model_service(request: Request) -> ModelService:
    container = request.app.state.container
    return ModelService(
        repository=container.model_repository,
        artifact_storage=container.artifact_storage,
    )


ModelServiceDep = Annotated[ModelService, Depends(get_model_service)]
