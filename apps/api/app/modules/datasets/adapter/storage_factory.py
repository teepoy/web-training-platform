from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker

from platform_runtime.sparse import DatasetPayloadStore
from app.modules.datasets.domain.storage_agg import DatasetStorageAgg
from app.shared.api.schemas import DatasetStorageMode
from app.shared.db.sql_repository import SqlRepository
from app.shared.domain.protocols import ArtifactStorage, LabelStudioClient


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
        repo: SqlRepository,
        storage: ArtifactStorage,
        payload_store: DatasetPayloadStore,
        ls_client: LabelStudioClient,
        session_factory: async_sessionmaker,
    ) -> None:
        self._repo = repo
        self._storage = storage
        self._payload_store = payload_store
        self._ls_client = ls_client
        self._session_factory = session_factory

    async def open(
        self, dataset_id: str, org_id: str | None = None
    ) -> DatasetStorageAgg:
        """Open a dataset storage backend by reading dataset metadata and
        dispatching to the correct implementation based on storage_mode."""
        dataset = await self._repo.get_dataset(dataset_id, org_id)
        if dataset is None:
            raise ValueError(f"Dataset not found: {dataset_id}")

        if dataset.storage_mode == DatasetStorageMode.DB_FULL:
            from app.modules.datasets.adapter.db_full_storage import (
                DbFullDatasetStorage,
            )

            return DbFullDatasetStorage(
                dataset_id=dataset_id,
                org_id=org_id,
                repo=self._repo,
                session_factory=self._session_factory,
                storage=self._storage,
                ls_client=self._ls_client,
            )

        if dataset.storage_mode == DatasetStorageMode.FILE_SHARD_SPARSE:
            from app.modules.datasets.adapter.sparse_storage import (
                SparseDatasetStorage,
            )

            return SparseDatasetStorage(
                dataset_id=dataset_id,
                org_id=org_id,
                storage=self._storage,
                payload_store=self._payload_store,
                ls_client=self._ls_client,
                session_factory=self._session_factory,
                repo=self._repo,
                dataset_type=dataset.dataset_type,
            )

        raise ValueError(f"Unknown storage_mode: {dataset.storage_mode}")
