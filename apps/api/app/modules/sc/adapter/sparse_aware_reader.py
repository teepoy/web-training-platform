from __future__ import annotations

from typing import Any, Protocol

from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory
from app.shared.api.schemas import Annotation, DatasetStorageMode


class SparseAwareUnderlyingReader(Protocol):
    async def get_dataset(
        self, dataset_id: str, org_id: str | None = None
    ) -> Any | None: ...

    async def list_samples(
        self, dataset_id: str, offset: int = 0, limit: int = 100
    ) -> tuple[list, int]: ...

    async def create_annotation(self, annotation: Annotation) -> Annotation: ...


class SparseAwareScDatasetReader:
    """SC dataset reader that dispatches list_samples based on storage_mode.

    Wraps an underlying reader for db_full datasets,
    and delegates list_samples/annotations to DatasetStorageAgg for
    file_shard_sparse datasets so SC view endpoints work for both
    storage modes.

    All other methods (get_dataset, create_annotation) pass through to
    the underlying reader.
    """

    def __init__(
        self,
        underlying: SparseAwareUnderlyingReader,
        storage_factory: DatasetStorageFactory,
    ) -> None:
        self._underlying = underlying
        self._storage_factory = storage_factory

    async def get_dataset(
        self, dataset_id: str, org_id: str | None = None
    ) -> Any | None:
        return await self._underlying.get_dataset(dataset_id, org_id=org_id)

    async def create_annotation(
        self, annotation: Annotation, *, dataset_id: str | None = None
    ) -> Annotation:
        if dataset_id is not None:
            ds = await self._underlying.get_dataset(dataset_id)
            mode = self._resolve_mode(ds)
            if mode == DatasetStorageMode.FILE_SHARD_SPARSE:
                org_id = getattr(ds, "org_id", None) if ds is not None else None
                storage = await self._storage_factory.open(
                    dataset_id, org_id=org_id or ""
                )
                await storage.create_annotations([annotation])
                return annotation
        return await self._underlying.create_annotation(annotation)

    @staticmethod
    def _resolve_mode(ds: Any | None) -> DatasetStorageMode:
        if ds is None or not hasattr(ds, "storage_mode"):
            return DatasetStorageMode.DB_FULL
        raw = ds.storage_mode
        if isinstance(raw, DatasetStorageMode):
            return raw
        try:
            return DatasetStorageMode(str(raw))
        except ValueError:
            return DatasetStorageMode.DB_FULL

    async def list_samples(
        self, dataset_id: str, *, offset: int = 0, limit: int = 50
    ) -> tuple[list, int]:
        ds = await self._underlying.get_dataset(dataset_id)
        mode = DatasetStorageMode.DB_FULL
        if ds is not None and hasattr(ds, "storage_mode"):
            raw_mode = ds.storage_mode
            if isinstance(raw_mode, DatasetStorageMode):
                mode = raw_mode
            else:
                try:
                    mode = DatasetStorageMode(str(raw_mode))
                except ValueError:
                    mode = DatasetStorageMode.DB_FULL

        if mode == DatasetStorageMode.FILE_SHARD_SPARSE:
            storage = await self._storage_factory.open(
                dataset_id, org_id=getattr(ds, "org_id", None) or ""
            )
            rows, total = await storage.list_samples(
                offset=offset,
                limit=limit,
            )
            return list(rows), total

        return await self._underlying.list_samples(
            dataset_id, offset=offset, limit=limit
        )
