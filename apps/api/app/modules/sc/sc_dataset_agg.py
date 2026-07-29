"""SC-specific operations over the canonical dataset storage aggregate."""

from __future__ import annotations

from typing import Protocol

from app.modules.storage.domain.storage_agg import DatasetStorageAgg
from app.shared.api.schemas import DatasetStorageMode


class ScDefectIdLookup(Protocol):
    async def map_defect_ids_to_sample_ids(
        self,
        dataset_id: str,
        defect_ids: set[str],
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
            existing = await self._storage.existing_sample_ids(defect_ids)
            return {defect_id: defect_id for defect_id in existing}

        if self._storage.storage_mode == DatasetStorageMode.DB_FULL:
            return await self._defect_id_lookup.map_defect_ids_to_sample_ids(
                self._storage.dataset_id,
                defect_ids,
            )

        raise ValueError(f"Unsupported storage mode: {self._storage.storage_mode}")
