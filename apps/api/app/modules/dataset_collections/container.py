from __future__ import annotations

from dataclasses import dataclass

from injector import Module, provider, singleton

from app.modules.dataset_collections.adapter.repositories import (
    DatasetCollectionSqlRepository,
)
from app.modules.dataset_collections.app.services import (
    CollectionModelAutomationService,
    CollectionSnapshotPublishingService,
    DatasetCollectionService,
)
from app.modules.dataset_collections.domain.repository import (
    DatasetCollectionRepository,
)
from app.modules.dataset_collections.port.local import (
    CollectionDatasetUsagePort,
    CollectionAutomationAdmissionPort,
    CollectionExportReaderPort,
    CollectionModelManagementPort,
    CollectionPredictionAutomationPort,
    CollectionSnapshotPublishingPort,
    DatasetCollectionManagementPort,
    DatasetCollectionRevisionReaderPort,
)
from app.shared.db.session import AppDatabaseSessionFactory


@dataclass
class DatasetCollectionsContext:
    repository: DatasetCollectionRepository
    service: DatasetCollectionService


class DatasetCollectionsModule(Module):
    @provider
    @singleton
    def provide_repository_impl(
        self, session_factory: AppDatabaseSessionFactory
    ) -> DatasetCollectionSqlRepository:
        return DatasetCollectionSqlRepository(session_factory.sessionmaker)

    @provider
    @singleton
    def provide_repository(
        self, repository: DatasetCollectionSqlRepository
    ) -> DatasetCollectionRepository:
        return repository

    @provider
    @singleton
    def provide_context(
        self,
        repository: DatasetCollectionRepository,
        service: DatasetCollectionService,
    ) -> DatasetCollectionsContext:
        return DatasetCollectionsContext(repository=repository, service=service)

    @provider
    @singleton
    def provide_management_port(
        self, service: DatasetCollectionService
    ) -> DatasetCollectionManagementPort:
        return service

    @provider
    @singleton
    def provide_usage_port(
        self, service: DatasetCollectionService
    ) -> CollectionDatasetUsagePort:
        return service

    @provider
    @singleton
    def provide_export_reader(
        self, service: DatasetCollectionService
    ) -> CollectionExportReaderPort:
        return service

    @provider
    @singleton
    def provide_automation_admission(
        self, service: DatasetCollectionService
    ) -> CollectionAutomationAdmissionPort:
        return service

    @provider
    @singleton
    def provide_revision_reader(
        self, service: DatasetCollectionService
    ) -> DatasetCollectionRevisionReaderPort:
        return service

    @provider
    @singleton
    def provide_model_management(
        self, service: CollectionModelAutomationService
    ) -> CollectionModelManagementPort:
        return service

    @provider
    @singleton
    def provide_prediction_automation(
        self, service: CollectionModelAutomationService
    ) -> CollectionPredictionAutomationPort:
        return service

    @provider
    @singleton
    def provide_snapshot_publishing(
        self, service: CollectionSnapshotPublishingService
    ) -> CollectionSnapshotPublishingPort:
        return service
