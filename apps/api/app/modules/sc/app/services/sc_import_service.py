from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from time import perf_counter
from typing import Any, Protocol, cast
from uuid import uuid4

from injector import inject
import polars as pl
import pyarrow as pa

from app.modules.datasets.domain.entities import DatasetRevisionOperation
from app.modules.datasets.port.local import DatasetRevisionPublisherPort
from app.modules.sc.domain.entities.sc_import import ScImportStatus
from app.modules.sc.domain.models import _coerce_naive_to_upstream_tz
from app.modules.sc.domain.upstream_reader import ScUpstreamReader
from app.modules.sc.port.local import ScImportProgressCallback
from app.modules.sc.schema import (
    SC_SOURCE_SCHEMA_VERSION,
    _build_v4_pyarrow_schema,
)
from app.shared.api.schemas import (
    Dataset,
    DatasetStorageMode,
    SPARSE_NO_LS,
    TaskSpec,
)
from app.modules.storage.domain.sparse import (
    ColumnSchema,
    DatasetManifest,
    DatasetPayloadStore,
    ShardEntry,
)
from app.modules.storage.port.local import (
    SparseColumnarImportSessionPort,
    SparseImportWriterFactoryPort,
)

logger = logging.getLogger(__name__)

# ── SC-specific helpers ─────────────────────────────────────────────────────


def _parse_source_inspection_time(value: str) -> datetime:
    return _coerce_naive_to_upstream_tz(datetime.fromisoformat(value))


def _process_memory_summary() -> str:
    """Return Linux process RSS/HWM details for import diagnostics."""
    try:
        with open("/proc/self/status") as status_file:
            values: dict[str, str] = {}
            for line in status_file:
                key, _, value = line.partition(":")
                if key in {"VmRSS", "VmHWM", "VmSize"}:
                    values[key] = value.strip()
        if values:
            return (
                f"rss={values.get('VmRSS', 'unknown')} "
                f"hwm={values.get('VmHWM', 'unknown')} "
                f"vmsize={values.get('VmSize', 'unknown')}"
            )
    except OSError:
        pass
    return "rss=unknown hwm=unknown vmsize=unknown"


def _transform_upstream_batch(
    batch: pa.RecordBatch,
    *,
    inspection_time: datetime,
    wafer_key: int,
    schema: pa.Schema | None = None,
) -> pa.Table:
    """Project one upstream batch to the closed identity-only shard schema."""
    frame: pl.DataFrame = pl.from_arrow(batch)  # type: ignore[assignment]
    required = {"defect_id"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"SC upstream batch is missing columns: {sorted(missing)}")

    del inspection_time, wafer_key
    defect_ids = frame["defect_id"].cast(pl.Utf8)
    sample_ids = pl.Series(
        "sample_id",
        [str(uuid4()) for _ in range(defect_ids.len())],
        dtype=pl.Utf8,
    )
    output = pl.DataFrame(
        {
            "sample_id": sample_ids,
            "defect_id": defect_ids.alias("defect_id"),
        }
    )
    table = cast(pa.Table, output.to_arrow())
    if schema is None:
        return table

    actual_names = set(table.column_names)
    expected_names = set(schema.names)
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        added = sorted(actual_names - expected_names)
        raise ValueError(
            "SC upstream schema changed during import: "
            f"missing columns={missing}, added columns={added}"
        )
    return table.select(schema.names).cast(schema, safe=False)


def _schema_columns(schema: pa.Schema) -> list[ColumnSchema]:
    """Serialize the complete concrete Arrow schema into the manifest."""
    return [ColumnSchema(name=field.name, type=str(field.type)) for field in schema]


class ScImportRepository(Protocol):
    async def create_dataset(
        self, dataset: Dataset, org_id: str | None = None
    ) -> Dataset: ...

    async def update_dataset_meta(
        self,
        dataset_id: str,
        meta_update: dict,
        *,
        org_id: str | None = None,
    ) -> Dataset | None: ...


class ScImportPayloadStore(Protocol):
    async def put_manifest(self, manifest: DatasetManifest, *, org_id: str) -> str: ...


class ScImportService:
    @inject
    def __init__(
        self,
        sparse_import_factory: SparseImportWriterFactoryPort,
        repository: ScImportRepository,
        payload_store: ScImportPayloadStore,
        revision_publisher: DatasetRevisionPublisherPort,
        upstream_reader: ScUpstreamReader,
        import_batch_rows: int,
        index_row_group_rows: int,
    ) -> None:
        if import_batch_rows <= 0:
            raise ValueError("import_batch_rows must be greater than zero")
        if index_row_group_rows <= 0:
            raise ValueError("index_row_group_rows must be greater than zero")
        self._repo = repository
        self._payload_store = payload_store
        self._revision_publisher = revision_publisher
        self._upstream = upstream_reader
        self._sparse_import_factory = sparse_import_factory
        self._import_batch_rows = import_batch_rows
        self._index_row_group_rows = index_row_group_rows

    async def submit_upstream_import(
        self,
        source_inspection_time: str,
        source_wafer_key: int,
        dataset_name: str,
        org_id: str,
        created_by: str = "system",
        label_space: list[str] | None = None,
        max_rows: int | None = None,
        on_progress: ScImportProgressCallback | None = None,
    ) -> ScImportStatus:
        """Import from the configured direct SC upstream image source."""
        return await self.submit_import(
            source_inspection_time=source_inspection_time,
            source_wafer_key=source_wafer_key,
            dataset_name=dataset_name,
            org_id=org_id,
            created_by=created_by,
            label_space=label_space,
            max_rows=max_rows,
            on_progress=on_progress,
        )

    async def submit_import(
        self,
        source_inspection_time: str,
        source_wafer_key: int,
        dataset_name: str,
        org_id: str,
        created_by: str = "system",
        label_space: list[str] | None = None,
        max_rows: int | None = None,
        on_progress: ScImportProgressCallback | None = None,
    ) -> ScImportStatus:
        # ── Pre-check: skip dataset creation when upstream has no data ──
        try:
            insp_dt = _parse_source_inspection_time(source_inspection_time)
            sample_count = await self._upstream.get_sample_count(
                insp_dt, source_wafer_key
            )
            if sample_count == 0:
                logger.info(
                    "SC import: upstream has no data for inspection_time=%s "
                    "wafer_key=%d — skipping dataset creation",
                    source_inspection_time,
                    source_wafer_key,
                )
                return ScImportStatus(
                    status="completed",
                    source_inspection_time=source_inspection_time,
                    source_wafer_key=source_wafer_key,
                    dataset_name=dataset_name,
                    imported_count=0,
                )
        except Exception as exc:
            logger.exception("SC import upstream pre-check failed")
            return await self._fail(
                f"Upstream pre-check failed: {exc}",
                source_inspection_time,
                source_wafer_key,
                dataset_name,
            )

        try:
            dataset = await self._create_dataset(
                source_inspection_time=source_inspection_time,
                source_wafer_key=source_wafer_key,
                dataset_name=dataset_name,
                org_id=org_id,
                created_by=created_by,
                label_space=label_space,
            )
        except Exception as exc:
            logger.exception("SC dataset creation failed")
            return await self._fail(
                f"Failed to create dataset: {exc}",
                source_inspection_time,
                source_wafer_key,
                dataset_name,
            )

        try:
            result = await self._run_direct_import(
                dataset_id=dataset.id,
                org_id=org_id,
                source_inspection_time=source_inspection_time,
                source_wafer_key=source_wafer_key,
                max_rows=max_rows,
                logger=logger,
                on_progress=on_progress,
            )
            imported_count_raw = result.get("imported_count", 0)
            imported_count: int = (
                int(imported_count_raw)
                if isinstance(imported_count_raw, (int, float))
                else 0
            )
            await self._revision_publisher.publish_sparse_revision(
                dataset_id=dataset.id,
                org_id=org_id,
                operation=DatasetRevisionOperation.INITIAL_IMPORT,
                created_by=created_by,
                provenance={
                    "source_connector": "sc",
                    "source_inspection_time": source_inspection_time,
                    "source_wafer_key": source_wafer_key,
                },
            )
            completed_status = ScImportStatus(
                status="completed",
                dataset_id=dataset.id,
                dataset_name=dataset_name,
                source_inspection_time=source_inspection_time,
                source_wafer_key=source_wafer_key,
                imported_count=imported_count,
            )
            return completed_status
        except Exception as e:
            logger.exception("Direct import failed, dataset=%s", dataset.id)
            return await self._fail(
                f"Direct import failed: {e}",
                source_inspection_time,
                source_wafer_key,
                dataset_name,
            )

    async def _run_direct_import(
        self,
        *,
        dataset_id: str,
        org_id: str,
        source_inspection_time: str,
        source_wafer_key: int,
        max_rows: int | None = None,
        logger: logging.Logger | logging.LoggerAdapter | None = None,
        on_progress: ScImportProgressCallback | None = None,
    ) -> dict[str, object]:
        """Direct sparse import that keeps request handling cooperative."""
        _payload_store = self._payload_store
        _upstream = self._upstream
        insp_dt = _parse_source_inspection_time(source_inspection_time)

        operator = self._sparse_import_factory.create(
            dataset_id=dataset_id,
            org_id=org_id,
            payload_store=cast(DatasetPayloadStore, _payload_store),
        )
        shard_entries: list[ShardEntry] = []
        total_rows = 0
        batch_size = self._import_batch_rows
        log = logger if logger is not None else logging.getLogger(__name__)

        async def publish_progress(imported_count: int) -> None:
            if on_progress is None:
                return
            await on_progress(
                ScImportStatus(
                    status="running",
                    dataset_id=dataset_id,
                    source_inspection_time=source_inspection_time,
                    source_wafer_key=source_wafer_key,
                    storage_mode="file_shard_sparse",
                    imported_count=imported_count,
                    remaining_count=max(target_rows - imported_count, 0),
                    dataset_name="",
                    error=None,
                )
            )

        start_time = perf_counter()
        log.info(
            "SC direct import starting: dataset_id=%s org_id=%s inspection_time=%s "
            "wafer_key=%s max_rows=%s batch_size=%s memory=%s",
            dataset_id,
            org_id,
            source_inspection_time,
            source_wafer_key,
            max_rows,
            batch_size,
            _process_memory_summary(),
        )
        total_rows_available = await _upstream.get_sample_count(
            insp_dt, source_wafer_key
        )
        target_rows = (
            min(total_rows_available, max_rows)
            if max_rows is not None
            else total_rows_available
        )
        log.info(
            "SC direct import row count resolved: dataset_id=%s total_available=%d "
            "target_rows=%d elapsed=%.3fs memory=%s",
            dataset_id,
            total_rows_available,
            target_rows,
            perf_counter() - start_time,
            _process_memory_summary(),
        )

        if total_rows_available == 0:
            log.info(
                "SC direct import has no rows: dataset_id=%s elapsed=%.3fs",
                dataset_id,
                perf_counter() - start_time,
            )
            return {"dataset_id": dataset_id, "imported_count": 0, "total_available": 0}

        if target_rows == 0:
            empty_schema = _build_v4_pyarrow_schema()
            empty_session = operator.begin_columnar_import(
                schema_columns=_schema_columns(empty_schema),
                schema_version=SC_SOURCE_SCHEMA_VERSION,
                index_row_group_rows=self._index_row_group_rows,
            )
            await empty_session.finalize()
            await publish_progress(0)
            log.info(
                "SC direct import target row count is zero: dataset_id=%s "
                "total_available=%d elapsed=%.3fs",
                dataset_id,
                total_rows_available,
                perf_counter() - start_time,
            )
            return {
                "dataset_id": dataset_id,
                "imported_count": 0,
                "total_available": total_rows_available,
            }

        await publish_progress(0)
        session: SparseColumnarImportSessionPort | None = None
        pyarrow_schema: pa.Schema | None = None
        transfer_seconds = 0.0
        transform_seconds = 0.0
        write_seconds = 0.0
        try:
            batch_number = 0
            stream = _upstream.stream_sample_batches(
                insp_dt,
                source_wafer_key,
                offset=0,
                count=target_rows,
                batch_rows=batch_size,
            )
            iterator = stream.__aiter__()
            while True:
                transfer_started = perf_counter()
                try:
                    record_batch = await anext(iterator)
                except StopAsyncIteration:
                    break
                transfer_seconds += perf_counter() - transfer_started
                batch_number += 1
                transform_started = perf_counter()
                table = await asyncio.to_thread(
                    _transform_upstream_batch,
                    record_batch,
                    inspection_time=insp_dt,
                    wafer_key=source_wafer_key,
                    schema=pyarrow_schema,
                )
                transform_seconds += perf_counter() - transform_started
                if session is None:
                    pyarrow_schema = table.schema
                    session = operator.begin_columnar_import(
                        schema_columns=_schema_columns(pyarrow_schema),
                        schema_version=SC_SOURCE_SCHEMA_VERSION,
                        index_row_group_rows=self._index_row_group_rows,
                    )
                write_started = perf_counter()
                shard_entry = await session.append(
                    table,
                    row_id_column="sample_id",
                    upstream_item_id_column="defect_id",
                )
                write_seconds += perf_counter() - write_started
                shard_entries.append(shard_entry)
                total_rows += table.num_rows
                await publish_progress(total_rows)
                log.info(
                    "SC direct import flushed columnar shard: dataset_id=%s "
                    "shard=%d rows=%d imported=%d/%d total_elapsed=%.3fs memory=%s",
                    dataset_id,
                    batch_number - 1,
                    table.num_rows,
                    total_rows,
                    target_rows,
                    perf_counter() - start_time,
                    _process_memory_summary(),
                )
                await asyncio.sleep(0)
            if total_rows != target_rows:
                raise RuntimeError(
                    f"upstream stream ended after {total_rows} rows; expected {target_rows}"
                )
            if session is None:
                raise RuntimeError("upstream stream returned no Arrow batches")
            manifest_started = perf_counter()
            await session.finalize()
            manifest_seconds = perf_counter() - manifest_started
        except BaseException:
            if session is not None:
                await session.abort()
            raise

        log.info(
            "SC direct import complete: dataset_id=%s imported=%d total_available=%d "
            "shards=%d elapsed=%.3fs transfer=%.3fs transform=%.3fs "
            "write=%.3fs manifest=%.3fs memory=%s",
            dataset_id,
            total_rows,
            total_rows_available,
            len(shard_entries),
            perf_counter() - start_time,
            transfer_seconds,
            transform_seconds,
            write_seconds,
            manifest_seconds,
            _process_memory_summary(),
        )

        return {
            "dataset_id": dataset_id,
            "imported_count": total_rows,
            "total_available": total_rows_available,
        }

    async def _create_dataset(
        self,
        *,
        source_inspection_time: str,
        source_wafer_key: int,
        dataset_name: str,
        org_id: str,
        created_by: str,
        label_space: list[str] | None,
    ) -> Dataset:
        dataset = Dataset(
            name=dataset_name,
            dataset_type="image_sc",
            task_spec=TaskSpec(task_type="sc", label_space=label_space or []),
            view_types=[
                "image_input_v1",
                "patch_image_v1",
                "review_image_v1",
            ],
            org_id=org_id,
            created_by=created_by,
            ls_project_id=SPARSE_NO_LS,
            storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE,
        )
        dataset = await self._repo.create_dataset(dataset, org_id=org_id)
        await self._payload_store.put_manifest(
            DatasetManifest(
                dataset_id=dataset.id,
                storage_mode=dataset.storage_mode.value,
                shard_count=0,
                total_rows=0,
                manifest_version="v3",
            ),
            org_id=org_id,
        )

        dataset_meta: dict[str, Any] = {
            "source_inspection_time": source_inspection_time,
            "source_wafer_key": source_wafer_key,
        }
        await self._repo.update_dataset_meta(
            dataset.id,
            dataset_meta,
            org_id=org_id,
        )
        return dataset

    async def _fail(
        self,
        error_message: str,
        source_inspection_time: str = "",
        source_wafer_key: int = 0,
        dataset_name: str = "",
    ) -> ScImportStatus:
        failed_status = ScImportStatus(
            status="failed",
            error=error_message,
            source_inspection_time=source_inspection_time,
            source_wafer_key=source_wafer_key,
            dataset_name=dataset_name,
        )
        return failed_status
