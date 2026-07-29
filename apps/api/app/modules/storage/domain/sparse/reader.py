"""In-memory parquet shard reader suitable for both API and worker runtimes."""

from __future__ import annotations

import io
import logging
from collections import OrderedDict
from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.parquet as pq

from app.modules.storage.domain.sparse.models import ColumnSchema

if TYPE_CHECKING:
    from app.shared.domain.runtime import ArtifactStorage

_logger = logging.getLogger(__name__)

_DEFAULT_TABLE_CACHE_SIZE = 64


class SparseManifestReader:
    """Reads parquet shard metadata and rows from in-memory bytes.

    All methods accept an ``ArtifactStorage`` protocol to fetch shard
    bytes on demand — no local disk I/O.

    Parsed pyarrow Tables are cached in a bounded LRU keyed by
    ``(shard_uri, columns_tuple)`` to avoid re-downloading and
    re-decoding the same shard for every paginated page request.
    Shards are content-addressed (uploaded once, then immutable), so
    cache invalidation isn't needed.
    """

    def __init__(self, table_cache_size: int = _DEFAULT_TABLE_CACHE_SIZE) -> None:
        self._table_cache: OrderedDict[tuple[str, tuple[str, ...] | None], pa.Table] = (
            OrderedDict()
        )
        self._table_cache_max = table_cache_size

    def _cache_get(self, shard_uri: str, columns: list[str] | None) -> pa.Table | None:
        key = (shard_uri, tuple(columns) if columns is not None else None)
        table = self._table_cache.get(key)
        if table is not None:
            self._table_cache.move_to_end(key)
        return table

    def _cache_put(
        self, shard_uri: str, columns: list[str] | None, table: pa.Table
    ) -> None:
        key = (shard_uri, tuple(columns) if columns is not None else None)
        self._table_cache[key] = table
        self._table_cache.move_to_end(key)
        while len(self._table_cache) > self._table_cache_max:
            self._table_cache.popitem(last=False)

    async def _load_table(
        self,
        shard_uri: str,
        storage: ArtifactStorage,
        columns: list[str] | None = None,
    ) -> pa.Table:
        cached = self._cache_get(shard_uri, columns)
        if cached is not None:
            return cached
        shard_bytes = await storage.get_bytes(shard_uri)
        table = pq.read_table(io.BytesIO(shard_bytes), columns=columns)
        self._cache_put(shard_uri, columns, table)
        return table

    async def read_shard_schema(
        self, shard_uri: str, storage: ArtifactStorage
    ) -> list[ColumnSchema]:
        shard_bytes = await storage.get_bytes(shard_uri)
        parquet_file = pq.ParquetFile(io.BytesIO(shard_bytes))
        return [
            ColumnSchema(name=f.name, type=str(f.type))
            for f in parquet_file.schema_arrow
        ]

    async def read_shard_summary(
        self, shard_uri: str, storage: ArtifactStorage
    ) -> dict[str, object]:
        shard_bytes = await storage.get_bytes(shard_uri)
        parquet_file = pq.ParquetFile(io.BytesIO(shard_bytes))
        metadata = parquet_file.metadata
        arrow_schema = parquet_file.schema_arrow
        return {
            "row_count": metadata.num_rows,
            "row_groups": metadata.num_row_groups,
            "column_names": arrow_schema.names,
            "approx_byte_size": len(shard_bytes),
        }

    async def read_row(
        self, shard_uri: str, row_index: int, storage: ArtifactStorage
    ) -> dict[str, object]:
        table = await self._load_table(shard_uri, storage)
        if row_index < 0 or row_index >= table.num_rows:
            raise IndexError(
                f"Row index {row_index} out of range [0, {table.num_rows})"
            )
        row_slice = table.slice(row_index, 1)
        return {col: row_slice.column(col)[0].as_py() for col in row_slice.column_names}

    async def read_row_batch(
        self,
        shard_uri: str,
        start: int,
        count: int,
        storage: ArtifactStorage,
        columns: list[str] | None = None,
    ) -> list[dict[str, object]]:
        table = await self._load_table(shard_uri, storage, columns)
        batch = table.slice(start, count)
        result: list[dict[str, object]] = []
        for i in range(batch.num_rows):
            result.append(
                {col: batch.column(col)[i].as_py() for col in batch.column_names}
            )
        return result

    async def read_rows(
        self,
        shard_uri: str,
        row_indices: list[int],
        storage: ArtifactStorage,
        columns: list[str] | None = None,
    ) -> dict[int, dict[str, object]]:
        """Read arbitrary rows after loading and decoding a shard once."""
        if not row_indices:
            return {}

        table = await self._load_table(shard_uri, storage, columns)
        invalid = [
            index for index in row_indices if index < 0 or index >= table.num_rows
        ]
        if invalid:
            raise IndexError(
                f"Row indices {invalid} out of range [0, {table.num_rows})"
            )

        return {
            index: {
                column: table.column(column)[index].as_py()
                for column in table.column_names
            }
            for index in row_indices
        }
