from __future__ import annotations

from dataclasses import dataclass

from injector import Module, inject, provider, singleton
from app.modules.storage.domain.sparse import DatasetPayloadStore

from app.modules.datasets.adapter.repositories.dataset_sql_repository import (
    DatasetSqlRepository,
)
from app.modules.storage.adapter.factory import DatasetStorageFactory
from app.modules.storage.adapter.sparse.import_operator import (
    SparseImportOperatorFactory,
)
from app.modules.storage.domain.data_plane.schemas import DataPlaneSchemaRegistry
from app.modules.storage.port.local import (
    DataPlaneSchemaRegistryPort,
    DatasetStorageFactoryPort,
    SparseImportWriterFactoryPort,
)
from app.shared.context import SharedInfra


@dataclass
class StorageContext:
    dataset_storage_factory: DatasetStorageFactory
    dataset_payload_store: DatasetPayloadStore
    sparse_import_factory: SparseImportOperatorFactory
    schema_registry: DataPlaneSchemaRegistry


def init_storage(shared: SharedInfra, repo: DatasetSqlRepository) -> StorageContext:
    payload_store = DatasetPayloadStore(storage=shared.artifact_storage)
    storage_factory = DatasetStorageFactory(
        repo=repo,
        storage=shared.artifact_storage,
        payload_store=payload_store,
        session_factory=shared.session_factory.sessionmaker,
    )
    return StorageContext(
        dataset_storage_factory=storage_factory,
        dataset_payload_store=payload_store,
        sparse_import_factory=SparseImportOperatorFactory(),
        schema_registry=DataPlaneSchemaRegistry.default(),
    )


class StorageModule(Module):
    @inject
    @provider
    @singleton
    def provide_storage_context(
        self,
        shared: SharedInfra,
        repository: DatasetSqlRepository,
    ) -> StorageContext:
        return init_storage(shared, repo=repository)

    @provider
    @singleton
    def provide_dataset_storage_factory(
        self, context: StorageContext
    ) -> DatasetStorageFactoryPort:
        return context.dataset_storage_factory

    @provider
    @singleton
    def provide_dataset_payload_store(
        self, context: StorageContext
    ) -> DatasetPayloadStore:
        return context.dataset_payload_store

    @provider
    @singleton
    def provide_sparse_import_writer_factory(
        self, context: StorageContext
    ) -> SparseImportWriterFactoryPort:
        return context.sparse_import_factory

    @provider
    @singleton
    def provide_data_plane_schema_registry(
        self, context: StorageContext
    ) -> DataPlaneSchemaRegistryPort:
        return context.schema_registry
