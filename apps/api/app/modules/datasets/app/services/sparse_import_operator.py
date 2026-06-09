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

import io
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pyarrow as pa

    from platform_runtime.sparse.models import (
        ColumnSchema,
        DatasetManifest,
        SampleLocator,
        ShardEntry,
    )
    from platform_runtime.sparse.store import DatasetPayloadStore


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

        from platform_runtime.sparse import SampleLocator

        table = pa.Table.from_pylist(rows, schema=pyarrow_schema)
        buf = io.BytesIO()
        pq.write_table(table, buf)
        data = buf.getvalue()

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
        from platform_runtime.sparse import DatasetManifest

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
