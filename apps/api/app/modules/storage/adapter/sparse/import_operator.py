"""Generic sparse shard persistence operator.

Owns Parquet shard writing, SampleLocator construction, payload-store
writes, and manifest finalization.  Schema-agnostic — the caller provides
the PyArrow schema as a parameter, keeping data-source-specific column
definitions co-located with the source adapter.

This operator is the canonical entrypoint for any data-source adapter
that writes ``file_shard_sparse`` datasets.  See
:class:`SparseImportOperator`.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import tempfile
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from app.modules.storage.domain.columnar_schemas import SPARSE_INDEX_SCHEMA

if TYPE_CHECKING:
    import pyarrow as pa

    from app.modules.storage.domain.sparse.models import (
        ColumnSchema,
        DatasetManifest,
        SampleLocator,
        ShardEntry,
    )
    from app.modules.storage.domain.sparse.store import DatasetPayloadStore


class SparseImportOperator:
    """Generic sparse shard persistence service.

    Parameters
    ----------
    dataset_id:
        Target dataset identifier.
    org_id:
        Organisation identifier used for object-store layout.
    payload_store:
        Shard and manifest persistence backend.
    logger:
        Optional logger for per-shard progress messages.
    """

    def __init__(
        self,
        *,
        dataset_id: str,
        org_id: str,
        payload_store: DatasetPayloadStore,
        logger: logging.Logger | logging.LoggerAdapter | None = None,
    ) -> None:
        self._dataset_id = dataset_id
        self._org_id = org_id
        self._payload_store = payload_store
        self._logger = logger

    # ------------------------------------------------------------------
    # shard write
    # ------------------------------------------------------------------

    async def flush_shard(
        self,
        *,
        shard_index: int,
        rows: list[dict[str, Any]],
        pyarrow_schema: pa.Schema,
        row_id_key: str = "sample_id",
    ) -> tuple[ShardEntry, dict[str, SampleLocator]]:
        """Write a Parquet shard batch to the payload store.

        Parameters
        ----------
        shard_index:
            Zero-based shard sequence number.
        rows:
            List of row dicts — each dict must contain a key matching
            *row_id_key* for SampleLocator construction.
        pyarrow_schema:
            Concrete PyArrow schema for table construction.  The caller
            is responsible for building a schema compatible with the
            row dict keys.
        row_id_key:
            Dict key used to derive each ``SampleLocator`` dict key and
            ``upstream_item_id``.  Defaults to ``"sample_id"`` — the
            canonical row identity.  SC importers that use defect_id
            as the row identity should pass ``row_id_key="sample_id"``
            (since SC sample_id is the defect_id).

        Returns
        -------
        tuple[ShardEntry, dict[str, SampleLocator]]
            The persisted shard metadata and a dict mapping each row's
            identity to its locator.
        """
        import pyarrow as pa
        import pyarrow.parquet as pq

        from app.modules.storage.domain.sparse import SampleLocator

        def _build_parquet_bytes() -> bytes:
            table = pa.Table.from_pylist(rows, schema=pyarrow_schema)
            buf = io.BytesIO()
            pq.write_table(table, buf)
            return buf.getvalue()

        data = await asyncio.to_thread(_build_parquet_bytes)

        shard_entry = await self._payload_store.put_shard(
            dataset_id=self._dataset_id,
            org_id=self._org_id,
            shard_index=shard_index,
            data=data,
            row_count=len(rows),
            format="parquet",
        )

        locators: dict[str, SampleLocator] = {}
        for row_idx, row in enumerate(rows):
            item_id = row[row_id_key]
            locators[item_id] = SampleLocator(
                dataset_id=self._dataset_id,
                shard_index=shard_index,
                row_index=row_idx,
                upstream_item_id=item_id,
            )

        if self._logger is not None:
            self._logger.info(
                "SparseImportOperator: shard %d flushed — %d rows, %d bytes, uri=%s",
                shard_index,
                len(rows),
                len(data),
                shard_entry.uri,
            )

        return shard_entry, locators

    def begin_columnar_import(
        self,
        *,
        schema_columns: list[ColumnSchema],
        schema_version: str,
        index_row_group_rows: int,
    ) -> SparseColumnarImportSession:
        return SparseColumnarImportSession(
            operator=self,
            schema_columns=schema_columns,
            schema_version=schema_version,
            index_row_group_rows=index_row_group_rows,
        )

    async def _flush_arrow_shard(
        self,
        *,
        shard_index: int,
        table: pa.Table,
    ) -> ShardEntry:
        import pyarrow.parquet as pq

        handle = tempfile.NamedTemporaryFile(suffix=".parquet", delete=False)
        handle.close()
        try:
            await asyncio.to_thread(
                pq.write_table,
                table,
                handle.name,
                compression="snappy",
            )
            return await self._payload_store.put_shard_file(
                dataset_id=self._dataset_id,
                org_id=self._org_id,
                shard_index=shard_index,
                path=handle.name,
                row_count=table.num_rows,
            )
        finally:
            await asyncio.to_thread(_unlink_if_exists, handle.name)

    # ------------------------------------------------------------------
    # manifest finalization
    # ------------------------------------------------------------------

    async def finalize_manifest(
        self,
        *,
        shard_entries: list[ShardEntry],
        sample_index: dict[str, SampleLocator],
        total_rows: int,
        shard_count: int,
        schema_columns: list[ColumnSchema],
        schema_version: str,
    ) -> DatasetManifest:
        """Build and persist the dataset manifest.

        After this call the payload store contains a complete
        ``manifest.json`` — the dataset payload is discoverable by
        downstream readers.

        Returns the constructed :class:`DatasetManifest` so callers can
        perform data-source-specific validation (e.g. schema version
        checks) before returning to the flow caller.
        """
        from app.modules.storage.domain.sparse import DatasetManifest

        manifest = DatasetManifest(
            dataset_id=self._dataset_id,
            storage_mode="file_shard_sparse",
            shard_count=shard_count,
            total_rows=total_rows,
            schema_columns=schema_columns,
            shards=shard_entries,
            sample_index=sample_index,
            schema_version=schema_version,
        )
        await self._payload_store.put_manifest(manifest, org_id=self._org_id)

        if self._logger is not None:
            self._logger.info(
                "SparseImportOperator: manifest finalized — %d rows across %d shards",
                total_rows,
                shard_count,
            )

        return manifest


class SparseImportOperatorFactory:
    def create(
        self,
        *,
        dataset_id: str,
        org_id: str,
        payload_store: DatasetPayloadStore,
    ) -> SparseImportOperator:
        return SparseImportOperator(
            dataset_id=dataset_id,
            org_id=org_id,
            payload_store=payload_store,
        )


class SparseColumnarImportSession:
    """Own one bounded columnar import and its manifest-v3 index lifecycle."""

    def __init__(
        self,
        *,
        operator: SparseImportOperator,
        schema_columns: list[ColumnSchema],
        schema_version: str,
        index_row_group_rows: int,
    ) -> None:
        if index_row_group_rows <= 0:
            raise ValueError("index_row_group_rows must be greater than zero")
        self._operator = operator
        self._schema_columns = schema_columns
        self._schema_version = schema_version
        self._index_row_group_rows = index_row_group_rows
        handle = tempfile.NamedTemporaryFile(suffix=".parquet", delete=False)
        handle.close()
        self._index_path = handle.name
        self._index_writer: Any | None = None
        self._shards: list[Any] = []
        self._total_rows = 0
        self._finalized = False
        self._index_uri: str | None = None

    async def append(
        self,
        table: pa.Table,
        *,
        row_id_column: str,
        upstream_item_id_column: str | None = None,
    ) -> ShardEntry:
        import pyarrow as pa
        import pyarrow.parquet as pq

        if self._finalized:
            raise RuntimeError("columnar import session is already finalized")
        if row_id_column not in table.column_names:
            raise ValueError(f"row identity column is missing: {row_id_column}")
        if (
            upstream_item_id_column is not None
            and upstream_item_id_column not in table.column_names
        ):
            raise ValueError(
                f"upstream item identity column is missing: {upstream_item_id_column}"
            )
        if table.num_rows == 0:
            raise ValueError("cannot append an empty sparse shard")

        metadata = dict(table.schema.metadata or {})
        metadata[b"schema_version"] = self._schema_version.encode("utf-8")
        table = table.replace_schema_metadata(metadata)

        shard_index = len(self._shards)
        entry = await self._operator._flush_arrow_shard(
            shard_index=shard_index,
            table=table,
        )
        identities = table[row_id_column].cast(pa.string())
        upstream_identities = (
            table[upstream_item_id_column].cast(pa.string())
            if upstream_item_id_column is not None
            else identities
        )
        index_table = pa.Table.from_arrays(
            [
                identities,
                pa.array([shard_index] * table.num_rows, type=pa.int32()),
                pa.array(range(table.num_rows), type=pa.int32()),
                upstream_identities,
            ],
            schema=SPARSE_INDEX_SCHEMA,
        )

        def _write_index() -> None:
            if self._index_writer is None:
                self._index_writer = pq.ParquetWriter(
                    self._index_path,
                    index_table.schema,
                    compression="snappy",
                )
            self._index_writer.write_table(
                index_table,
                row_group_size=self._index_row_group_rows,
            )

        try:
            await asyncio.to_thread(_write_index)
        except BaseException:
            with suppress(Exception):
                await self._operator._payload_store.delete_object(entry.uri)
            raise
        self._shards.append(entry)
        self._total_rows += table.num_rows
        return entry

    async def finalize(self) -> DatasetManifest:
        import pyarrow as pa
        import pyarrow.parquet as pq

        from app.modules.storage.domain.sparse import DatasetManifest

        if self._finalized:
            raise RuntimeError("columnar import session is already finalized")
        self._finalized = True
        try:
            if self._index_writer is not None:
                await asyncio.to_thread(self._index_writer.close)
                self._index_writer = None
            else:
                empty_index = pa.Table.from_pylist([], schema=SPARSE_INDEX_SCHEMA)
                await asyncio.to_thread(
                    pq.write_table,
                    empty_index,
                    self._index_path,
                    compression="snappy",
                )
            index = await self._operator._payload_store.put_index_file(
                dataset_id=self._operator._dataset_id,
                org_id=self._operator._org_id,
                path=self._index_path,
                row_count=self._total_rows,
            )
            self._index_uri = index.uri
            manifest = DatasetManifest(
                dataset_id=self._operator._dataset_id,
                storage_mode="file_shard_sparse",
                shard_count=len(self._shards),
                total_rows=self._total_rows,
                schema_columns=self._schema_columns,
                shards=self._shards,
                sample_index={},
                index=index,
                manifest_version="v3",
                schema_version=self._schema_version,
            )
            await self._operator._payload_store.put_manifest(
                manifest,
                org_id=self._operator._org_id,
            )
            return manifest
        except BaseException:
            await self.abort()
            raise
        finally:
            await asyncio.to_thread(_unlink_if_exists, self._index_path)

    async def abort(self) -> None:
        if self._index_writer is not None:
            with suppress(Exception):
                await asyncio.to_thread(self._index_writer.close)
            self._index_writer = None
        for shard in self._shards:
            with suppress(Exception):
                await self._operator._payload_store.delete_object(shard.uri)
        if self._index_uri is not None:
            with suppress(Exception):
                await self._operator._payload_store.delete_object(self._index_uri)
        await asyncio.to_thread(_unlink_if_exists, self._index_path)


def _unlink_if_exists(path: str) -> None:
    with suppress(FileNotFoundError):
        os.unlink(path)
