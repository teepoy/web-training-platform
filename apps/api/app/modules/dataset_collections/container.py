from __future__ import annotations

from dataclasses import dataclass

from injector import Module, provider, singleton

from app.modules.dataset_collections.adapter.repositories import (
    DatasetCollectionSqlRepository,
)
from app.modules.dataset_collections.app.services import DatasetCollectionService
from app.modules.dataset_collections.domain.repository import (
    DatasetCollectionRepository,
)
from app.modules.dataset_collections.port.local import (
    CollectionDatasetUsagePort,
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
    def provide_revision_reader(
        self, service: DatasetCollectionService
    ) -> DatasetCollectionRevisionReaderPort:
        return service
