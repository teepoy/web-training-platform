"""SC-specific operations over the canonical dataset storage aggregate."""

from __future__ import annotations

from typing import Protocol, cast

from app.modules.storage.domain.storage_agg import DatasetStorageAgg
from app.shared.api.schemas import DatasetStorageMode


class ScDefectIdLookup(Protocol):
    async def map_defect_ids_to_sample_ids(
        self,
        dataset_id: str,
        defect_ids: set[str],
    ) -> dict[str, str]: ...


class ScSparseUpstreamIdentityLookup(Protocol):
    async def map_upstream_item_ids_to_sample_ids(
        self, upstream_item_ids: set[str]
    ) -> dict[str, str]: ...


class ScDatasetAgg:
    """Adds SC identity semantics without duplicating storage access paths."""

    def __init__(
        self,
        storage: DatasetStorageAgg,
        defect_id_lookup: ScDefectIdLookup,
    ) -> None:
        self._storage = storage
        self._defect_id_lookup = defect_id_lookup

    async def map_defect_ids_to_sample_ids(
        self,
        defect_ids: set[str],
    ) -> dict[str, str]:
        if not defect_ids:
            return {}

        if self._storage.storage_mode == DatasetStorageMode.FILE_SHARD_SPARSE:
            sparse_lookup = cast(ScSparseUpstreamIdentityLookup, self._storage)
            return await sparse_lookup.map_upstream_item_ids_to_sample_ids(defect_ids)

        if self._storage.storage_mode == DatasetStorageMode.DB_FULL:
            return await self._defect_id_lookup.map_defect_ids_to_sample_ids(
                self._storage.dataset_id,
                defect_ids,
            )

        raise ValueError(f"Unsupported storage mode: {self._storage.storage_mode}")
