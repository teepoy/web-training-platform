from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING

import pyarrow.parquet as pq

from app.modules.datasets.domain.entities.dataset_payload import ColumnSchema

if TYPE_CHECKING:
    from app.shared.domain.protocols import ArtifactStorage

_logger = logging.getLogger(__name__)


class SparseManifestReader:
    """Reads parquet shard metadata and rows from in-memory bytes.

    All methods accept an ``ArtifactStorage`` protocol to fetch shard
    bytes on demand — no local disk I/O.
    """

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
        shard_bytes = await storage.get_bytes(shard_uri)
        table = pq.read_table(io.BytesIO(shard_bytes))
        if row_index < 0 or row_index >= table.num_rows:
            raise IndexError(
                f"Row index {row_index} out of range [0, {table.num_rows})"
            )
        row_slice = table.slice(row_index, 1)
        return {col: row_slice.column(col)[0].as_py() for col in row_slice.column_names}

    async def read_row_batch(
        self, shard_uri: str, start: int, count: int, storage: ArtifactStorage
    ) -> list[dict[str, object]]:
        shard_bytes = await storage.get_bytes(shard_uri)
        table = pq.read_table(io.BytesIO(shard_bytes))
        batch = table.slice(start, count)
        result: list[dict[str, object]] = []
        for i in range(batch.num_rows):
            result.append(
                {col: batch.column(col)[i].as_py() for col in batch.column_names}
            )
        return result
