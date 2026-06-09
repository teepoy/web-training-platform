from __future__ import annotations

from dataclasses import dataclass

from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory
from app.modules.datasets.app.services.dataset_capability_guard import (
    assert_not_sparse,
)
from app.modules.datasets.app.services.dataset_service import DatasetService
from platform_runtime.sparse import DatasetPayloadStore
from app.modules.datasets.domain.repository import DatasetRepository
from app.modules.datasets.port.dataset_reader import DatasetReader
from app.shared.context import SharedInfra
from app.shared.db.sql_repository import SqlRepository


@dataclass
class DatasetsContext:
    dataset_repository: DatasetRepository
    dataset_reader: DatasetReader
    dataset_payload_store: DatasetPayloadStore
    dataset_service: DatasetService
    dataset_storage_factory: DatasetStorageFactory


def init_datasets(shared: SharedInfra) -> DatasetsContext:
    repo = SqlRepository(session_factory=shared.session_factory)
    store = DatasetPayloadStore(storage=shared.artifact_storage)
    storage_factory = DatasetStorageFactory(
        repo=repo,
        storage=shared.artifact_storage,
        payload_store=store,
        ls_client=shared.label_studio_client,
        session_factory=shared.session_factory,
    )
    dataset_service = DatasetService(
        repository=repo,
        storage_factory=storage_factory,
        ls_client=shared.label_studio_client,
        storage=shared.artifact_storage,
        payload_store=store,
        capability_guard=assert_not_sparse,
        config=shared.config,
    )
    return DatasetsContext(
        dataset_repository=repo,
        dataset_reader=repo,
        dataset_payload_store=store,
        dataset_service=dataset_service,
        dataset_storage_factory=storage_factory,
    )
