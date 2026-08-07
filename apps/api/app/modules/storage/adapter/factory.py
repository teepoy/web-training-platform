from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modules.storage.domain.sparse import DatasetPayloadStore
from app.modules.storage.domain.storage_agg import DatasetStorageAgg
from app.shared.api.schemas import Dataset, DatasetStorageMode
from app.modules.datasets.adapter.repositories.dataset_sql_repository import (
    DatasetSqlRepository,
)
from app.shared.domain.protocols import ArtifactStorage


class DatasetStorageFactory:
    """Create the right DatasetStorageAgg implementation for a given storage_mode.

    Usage in route handlers::

        async def handler(
            dataset_id: str,
            org_id: str,
            factory: DatasetStorageFactory = Depends(get_dataset_storage_factory),
            ...
        ):
            storage = await factory.open(dataset_id, org_id)
            samples, total = await storage.list_samples(0, 50)
    """

    def __init__(
        self,
        repo: DatasetSqlRepository,
        storage: ArtifactStorage,
        payload_store: DatasetPayloadStore,
        session_factory: async_sessionmaker,
        prediction_compaction_memory_limit: str,
        prediction_compaction_temp_limit: str,
        prediction_compaction_row_group_rows: int,
    ) -> None:
        self._repo = repo
        self._storage = storage
        self._payload_store = payload_store
        self._session_factory = session_factory
        self._prediction_compaction_memory_limit = prediction_compaction_memory_limit
        self._prediction_compaction_temp_limit = prediction_compaction_temp_limit
        self._prediction_compaction_row_group_rows = (
            prediction_compaction_row_group_rows
        )

    async def open(self, dataset_id: str, org_id: str) -> DatasetStorageAgg:
        """Open a dataset storage backend by reading dataset metadata and
        dispatching to the correct implementation based on storage_mode."""
        dataset = await self._repo.get_dataset(dataset_id, org_id)
        if dataset is None:
            raise ValueError(f"Dataset not found: {dataset_id}")

        return await self.open_from_metadata(dataset, org_id)

    async def open_from_metadata(
        self,
        dataset: Dataset,
        org_id: str,
    ) -> DatasetStorageAgg:
        """Open a backend without re-reading already-authorized metadata."""
        dataset_id = dataset.id

        if dataset.storage_mode == DatasetStorageMode.DB_FULL:
            from app.modules.storage.adapter.db_full.storage import (
                DbFullDatasetStorage,
            )

            return DbFullDatasetStorage(
                dataset_id=dataset_id,
                org_id=org_id,
                dataset_metadata=dataset,
                repo=self._repo,
                session_factory=self._session_factory,
                storage=self._storage,
            )

        if dataset.storage_mode == DatasetStorageMode.FILE_SHARD_SPARSE:
            from app.modules.storage.adapter.sparse.storage import (
                SparseDatasetStorage,
            )

            return SparseDatasetStorage(
                dataset_id=dataset_id,
                org_id=org_id,
                dataset_metadata=dataset,
                storage=self._storage,
                payload_store=self._payload_store,
                session_factory=self._session_factory,
                repo=self._repo,
                dataset_type=dataset.dataset_type,
                prediction_compaction_memory_limit=(
                    self._prediction_compaction_memory_limit
                ),
                prediction_compaction_temp_limit=self._prediction_compaction_temp_limit,
                prediction_compaction_row_group_rows=(
                    self._prediction_compaction_row_group_rows
                ),
            )

        raise ValueError(f"Unknown storage_mode: {dataset.storage_mode}")
