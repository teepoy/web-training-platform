from __future__ import annotations

from app.shared.api.schemas import DatasetStorageMode
from app.shared.db.sql_repository import SqlRepository
from app.modules.datasets.application.sample_access.base import (
    SampleAccess,
    StorageModeNotSupported,
)
from app.modules.datasets.application.sample_access.db_full import DbFullSampleAccess


class SampleAccessFactory:
    """Create the right SampleAccess implementation for a given storage_mode.

    Usage in route handlers::

        def handler(
            dataset_id: str,
            factory: SampleAccessFactory = Depends(get_sample_access_factory),
            ...
        ):
            dataset = await repo.get_dataset(dataset_id)
            access = factory.create(dataset.storage_mode)
            samples, total = await access.list_samples(dataset_id, 0, 50)
    """

    def __init__(self, repo: SqlRepository) -> None:
        self._db_full = DbFullSampleAccess(repo)

    def create(self, storage_mode: DatasetStorageMode) -> SampleAccess:
        if storage_mode == DatasetStorageMode.DB_FULL:
            return self._db_full
        if storage_mode == DatasetStorageMode.FILE_SHARD_SPARSE:
            return _SparseSampleAccess()
        raise ValueError(f"Unknown storage_mode: {storage_mode}")


class _SparseSampleAccess(SampleAccess):
    """Phase 1 sparse access: no operations supported yet."""

    _MODE = "file_shard_sparse"

    def capabilities(self) -> dict[str, bool]:
        return {
            "can_create_samples": False,
            "can_list_samples": False,
            "can_annotate": False,
            "can_train": False,
            "can_predict": False,
            "can_export": False,
            "can_similarity_search": False,
            "can_random_sampling": False,
        }

    async def create_samples(self, samples):
        raise StorageModeNotSupported("create_samples", self._MODE)

    async def get_sample(self, sample_id: str):
        raise StorageModeNotSupported("get_sample", self._MODE)

    async def list_samples(self, dataset_id: str, offset: int = 0, limit: int = 50):
        raise StorageModeNotSupported("list_samples", self._MODE)

    async def list_samples_with_labels(
        self,
        dataset_id,
        offset=0,
        limit=50,
        label_filter=None,
        order_by="id",
        sample_ids=None,
    ):
        raise StorageModeNotSupported("list_samples_with_labels", self._MODE)

    async def list_annotations(self, *, dataset_id=None, sample_id=None, limit=None):
        raise StorageModeNotSupported("list_annotations", self._MODE)

    async def get_annotation_stats(self, dataset_id: str):
        raise StorageModeNotSupported("get_annotation_stats", self._MODE)

    async def get_random_samples(self, dataset_id: str, limit: int = 100):
        raise StorageModeNotSupported("get_random_samples", self._MODE)

    async def similarity_search(self, embedding, dataset_id, k, exclude_id=""):
        raise StorageModeNotSupported("similarity_search", self._MODE)

    async def prediction_summary(self, dataset_id: str):
        raise StorageModeNotSupported("prediction_summary", self._MODE)

    async def update_sample(self, sample_id: str, *, image_uris=None, ls_task_id=None):
        raise StorageModeNotSupported("update_sample", self._MODE)
