from __future__ import annotations

from dataclasses import dataclass

from injector import Module, inject, provider, singleton

from app.modules.models.adapter.repositories.repository import ModelArtifactRepository
from app.modules.models.app.services.model_service import ModelService
from app.modules.models.domain.repository import ModelRepository
from app.modules.models.port.local import ModelCatalogPort, ModelManagementPort
from app.shared.context import SharedInfra
from app.shared.db.session import AppDatabaseSessionFactory
from app.shared.domain.protocols import ArtifactStorage as ArtifactStoragePort


@dataclass
class ModelsContext:
    model_repository: ModelArtifactRepository
    model_service: ModelService


def init_models(shared: SharedInfra) -> ModelsContext:
    repo = ModelArtifactRepository(session_factory=shared.session_factory.sessionmaker)
    svc = ModelService(repository=repo, artifact_storage=shared.artifact_storage)
    return ModelsContext(model_repository=repo, model_service=svc)


class ModelsModule(Module):
    @inject
    @provider
    @singleton
    def provide_models_context(
        self,
        session_factory: AppDatabaseSessionFactory,
        artifact_storage: ArtifactStoragePort,
    ) -> ModelsContext:
        repo = ModelArtifactRepository(session_factory=session_factory.sessionmaker)
        svc = ModelService(repository=repo, artifact_storage=artifact_storage)
        return ModelsContext(model_repository=repo, model_service=svc)

    @provider
    @singleton
    def provide_model_repository(self, context: ModelsContext) -> ModelRepository:
        return context.model_repository

    @provider
    @singleton
    def provide_model_service(self, context: ModelsContext) -> ModelService:
        return context.model_service

    @provider
    @singleton
    def provide_model_management(self, service: ModelService) -> ModelManagementPort:
        return service

    @provider
    @singleton
    def provide_model_catalog(self, context: ModelsContext) -> ModelCatalogPort:
        return context.model_repository
