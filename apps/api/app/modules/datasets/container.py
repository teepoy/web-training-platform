from __future__ import annotations

from dataclasses import dataclass

from injector import Module, inject, provider, singleton

from app.modules.datasets.adapter.repositories.dataset_sql_repository import (
    DatasetSqlRepository,
)
from app.shared.adapter.repositories.artifact_lookup_repository import (
    ArtifactSqlLookupRepository,
)
from app.modules.datasets.app.services.dataset_service import DatasetService
from app.modules.datasets.app.services.dataset_deletion_guard import (
    DatasetDeletionGuard,
)
from app.modules.datasets.app.services.sample_similarity import SampleSimilarityService
from app.modules.datasets.domain.repository import (
    ArtifactLookupRepository,
    DatasetRepository,
)
from app.modules.datasets.port.dataset_reader import DatasetReader
from app.modules.datasets.port.local import (
    DatasetDeletionGuardPort,
    IDatasetService,
    SampleSimilarityPort,
)
from app.modules.dataset_collections.port.local import CollectionDatasetUsagePort
from app.modules.prediction.port.local import PredictionDatasetUsagePort
from app.modules.training.port.local import TrainingDatasetUsagePort
from app.modules.storage.container import StorageContext
from app.shared.context import SharedInfra


@dataclass
class DatasetsContext:
    dataset_repository: DatasetRepository
    artifact_lookup_repository: ArtifactLookupRepository
    dataset_reader: DatasetReader
    dataset_service: DatasetService
    sample_similarity_service: SampleSimilarityService


def init_datasets(
    shared: SharedInfra,
    *,
    repository: DatasetSqlRepository,
    artifact_lookup_repository: ArtifactLookupRepository,
    storage: StorageContext,
) -> DatasetsContext:
    dataset_service = DatasetService(
        repository=repository,
        storage_factory=storage.dataset_storage_factory,
        payload_store=storage.dataset_payload_store,
        config=shared.config,
    )
    sample_similarity_service = SampleSimilarityService(
        storage_factory=storage.dataset_storage_factory
    )
    return DatasetsContext(
        dataset_repository=repository,
        artifact_lookup_repository=artifact_lookup_repository,
        dataset_reader=repository,
        dataset_service=dataset_service,
        sample_similarity_service=sample_similarity_service,
    )


class DatasetsModule(Module):
    @inject
    @provider
    @singleton
    def provide_dataset_deletion_guard(
        self,
        training_usage: TrainingDatasetUsagePort,
        prediction_usage: PredictionDatasetUsagePort,
        collection_usage: CollectionDatasetUsagePort,
    ) -> DatasetDeletionGuardPort:
        return DatasetDeletionGuard(
            training_usage=training_usage,
            prediction_usage=prediction_usage,
            collection_usage=collection_usage,
        )

    @inject
    @provider
    @singleton
    def provide_artifact_lookup_repository_impl(
        self, shared: SharedInfra
    ) -> ArtifactSqlLookupRepository:
        return ArtifactSqlLookupRepository(
            session_factory=shared.session_factory.sessionmaker
        )

    @inject
    @provider
    @singleton
    def provide_datasets_context(
        self,
        shared: SharedInfra,
        repository: DatasetSqlRepository,
        artifact_lookup_repository: ArtifactSqlLookupRepository,
        storage: StorageContext,
    ) -> DatasetsContext:
        return init_datasets(
            shared,
            repository=repository,
            artifact_lookup_repository=artifact_lookup_repository,
            storage=storage,
        )

    @provider
    @singleton
    def provide_dataset_service(self, context: DatasetsContext) -> DatasetService:
        return context.dataset_service

    @provider
    @singleton
    def provide_dataset_service_port(self, context: DatasetsContext) -> IDatasetService:
        return context.dataset_service

    @provider
    @singleton
    def provide_sample_similarity_port(
        self, context: DatasetsContext
    ) -> SampleSimilarityPort:
        return context.sample_similarity_service

    @provider
    @singleton
    def provide_dataset_repository(self, context: DatasetsContext) -> DatasetRepository:
        return context.dataset_repository

    @provider
    @singleton
    def provide_artifact_lookup_repository(
        self, context: DatasetsContext
    ) -> ArtifactLookupRepository:
        return context.artifact_lookup_repository

    @provider
    @singleton
    def provide_dataset_reader(self, context: DatasetsContext) -> DatasetReader:
        return context.dataset_reader
