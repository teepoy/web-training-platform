from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pyarrow.parquet as pq

from app.modules.storage.domain.sparse.models import SampleLocator, SparseIndexEntry
from app.shared.domain.runtime import ArtifactStorage


class SparseIndexReader:
    """Predicate-pushed reader for manifest-v3 sample locator indexes.

    The object is streamed once into a local temporary file. Parquet row-group
    statistics then answer ID lookups without creating a Python locator map.
    """

    def __init__(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory(prefix="sparse-index-")
        self._paths: dict[str, Path] = {}
        self._lock = asyncio.Lock()

    async def _local_path(
        self, entry: SparseIndexEntry, storage: ArtifactStorage
    ) -> Path:
        cached = self._paths.get(entry.uri)
        if (
            cached is not None
            and cached.is_file()
            and cached.stat().st_size == entry.byte_size
        ):
            return cached
        async with self._lock:
            cached = self._paths.get(entry.uri)
            if (
                cached is not None
                and cached.is_file()
                and cached.stat().st_size == entry.byte_size
            ):
                return cached
            path = Path(self._temporary_directory.name) / "sample-index.parquet"
            await storage.get_file(entry.uri, str(path))
            if path.stat().st_size != entry.byte_size:
                path.unlink(missing_ok=True)
                raise ValueError("sparse index byte size does not match manifest")
            await asyncio.to_thread(pq.read_metadata, path)
            self._paths = {entry.uri: path}
            return path

    async def lookup_many(
        self,
        entry: SparseIndexEntry,
        sample_ids: list[str] | set[str],
        *,
        dataset_id: str,
        storage: ArtifactStorage,
    ) -> dict[str, SampleLocator]:
        wanted = sorted({str(sample_id) for sample_id in sample_ids})
        if not wanted:
            return {}
        path = await self._local_path(entry, storage)
        table = await asyncio.to_thread(
            pq.read_table,
            path,
            columns=["sample_id", "shard_index", "row_index", "upstream_item_id"],
            filters=[("sample_id", "in", wanted)],
        )
        result: dict[str, SampleLocator] = {}
        for sample_id, shard_index, row_index, upstream_item_id in zip(
            table["sample_id"].to_pylist(),
            table["shard_index"].to_pylist(),
            table["row_index"].to_pylist(),
            table["upstream_item_id"].to_pylist(),
            strict=True,
        ):
            result[str(sample_id)] = SampleLocator(
                dataset_id=dataset_id,
                shard_index=int(shard_index),
                row_index=int(row_index),
                upstream_item_id=(
                    str(upstream_item_id) if upstream_item_id is not None else None
                ),
            )
        return result

    async def all_sample_ids(
        self,
        entry: SparseIndexEntry,
        *,
        storage: ArtifactStorage,
    ) -> list[str]:
        path = await self._local_path(entry, storage)
        table = await asyncio.to_thread(pq.read_table, path, columns=["sample_id"])
        return [str(value) for value in table["sample_id"].to_pylist()]
