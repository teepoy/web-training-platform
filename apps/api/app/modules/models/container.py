from __future__ import annotations

from dataclasses import dataclass

from app.modules.models.adapter.repositories.repository import ModelArtifactRepository
from app.modules.models.app.services.model_service import ModelService
from app.shared.context import SharedInfra


@dataclass
class ModelsContext:
    model_repository: ModelArtifactRepository
    model_service: ModelService


def init_models(shared: SharedInfra) -> ModelsContext:
    repo = ModelArtifactRepository(session_factory=shared.session_factory)
    svc = ModelService(repository=repo, artifact_storage=shared.artifact_storage)
    return ModelsContext(model_repository=repo, model_service=svc)
