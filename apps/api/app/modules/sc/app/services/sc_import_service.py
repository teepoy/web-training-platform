from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from time import perf_counter
from typing import Any, Protocol, cast

from injector import inject
import polars as pl
import pyarrow as pa

from app.modules.storage.port.local import SparseImportWriterFactoryPort
from app.modules.sc.domain.entities.sc_import import ScImportStatus
from app.modules.sc.domain.models import _coerce_naive_to_upstream_tz
from app.modules.sc.domain.upstream_reader import ScUpstreamReader
from app.modules.sc.port.local import ScImportProgressCallback
from app.modules.sc.app.services.import_rows import (
    _geometry_from_inspection,
)
from app.modules.sc.schema import (
    SC_SPARSE_SHARD_SCHEMA_V2,
    _build_v2_pyarrow_schema,
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

logger = logging.getLogger(__name__)

# ── SC-specific helpers ─────────────────────────────────────────────────────


def _parse_source_inspection_time(value: str) -> datetime:
    return _coerce_naive_to_upstream_tz(datetime.fromisoformat(value))


def _patch_sample_to_parquet_row(
    ps: Any, images: list[dict[str, object]]
) -> dict[str, Any]:
    inspection_time_str = ""
    if ps.inspection_time is not None:
        dt = ps.inspection_time
        dt = _coerce_naive_to_upstream_tz(dt)
        inspection_time_str = dt.isoformat()

    review_images = getattr(ps, "review_images", []) or []
    has_review = 1 if review_images else 0

    return {
        "sample_id": ps.sample_id,
        "defect_id": ps.defect_id,
        "inspection_time": inspection_time_str,
        "wafer_key": ps.wafer_key,
        "wafer_x": ps.wafer_x,
        "wafer_y": ps.wafer_y,
        "die_x": ps.die_x,
        "die_y": ps.die_y,
        "rough_bin": ps.rough_bin,
        "class_number": ps.class_number,
        "test_id": ps.test_id,
        "lot_id": ps.lot_id,
        "has_review": has_review,
        "images": images,
    }


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
    schema: pa.Schema,
) -> pa.Table:
    """Project one upstream batch directly into the SC sparse Arrow schema."""
    frame: pl.DataFrame = pl.from_arrow(batch)  # type: ignore[assignment]
    required = {
        "defect_id",
        "wafer_x",
        "wafer_y",
        "die_x",
        "die_y",
        "rough_bin",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"SC upstream batch is missing columns: {sorted(missing)}")

    inspection_value = inspection_time.isoformat()
    defect_id = pl.col("defect_id").cast(pl.Utf8)

    def patch_image(image_type: str, role: str) -> pl.Expr:
        filename = f"{image_type}.png"
        return pl.struct(
            pl.concat_str([defect_id, pl.lit(f"_{image_type}")]).alias("image_id"),
            pl.lit(image_type).alias("image_type"),
            pl.lit(role).alias("role"),
            pl.lit("image/png").alias("content_type"),
            pl.lit(filename).alias("filename"),
            pl.lit(None).cast(pl.Binary).alias("bytes"),
            pl.lit(None).cast(pl.Int32).alias("review_image_id"),
            pl.concat_str(
                [
                    pl.lit(f"mock-sc://patch/{inspection_value}/{wafer_key}/"),
                    defect_id,
                    pl.lit(f"/{filename}"),
                ]
            ).alias("source_uri"),
        )

    optional_expressions: list[pl.Expr] = []
    for column, dtype, default in (
        ("class_number", pl.Int32, None),
        ("test_id", pl.Int32, None),
        ("lot_id", pl.Utf8, ""),
    ):
        if column not in frame.columns:
            optional_expressions.append(pl.lit(default).cast(dtype).alias(column))
    if optional_expressions:
        frame = frame.with_columns(optional_expressions)

    output = frame.with_columns(
        defect_id.alias("sample_id"),
        defect_id.alias("defect_id"),
        pl.lit(inspection_value).cast(pl.Utf8).alias("inspection_time"),
        pl.lit(wafer_key).cast(pl.Int32).alias("wafer_key"),
        pl.col("wafer_x").cast(pl.Int32),
        pl.col("wafer_y").cast(pl.Int32),
        pl.col("die_x").cast(pl.Int32),
        pl.col("die_y").cast(pl.Int32),
        pl.col("rough_bin").cast(pl.Int32),
        pl.col("class_number").cast(pl.Int32),
        pl.col("test_id").cast(pl.Int32),
        pl.col("lot_id").cast(pl.Utf8),
        pl.lit(0).cast(pl.Int32).alias("has_review"),
        pl.concat_list(
            [
                patch_image("template", "patch_template"),
                patch_image("defective", "patch_defective"),
                patch_image("difference", "patch_difference"),
            ]
        ).alias("images"),
    ).select(schema.names)
    return cast(pa.Table, output.to_arrow()).cast(schema, safe=False)


async def _build_image_structs(
    *,
    patch_sample: Any,
    inspection_time: Any,
    wafer_key: int,
) -> list[dict[str, object]]:
    images: list[dict[str, object]] = []
    defect_id = patch_sample.defect_id
    insp_time_str = (
        inspection_time.isoformat()
        if hasattr(inspection_time, "isoformat")
        else str(inspection_time)
    )

    review_images: list[Any] = getattr(patch_sample, "review_images", []) or []
    for review_image in review_images:
        images.append(
            {
                "image_id": str(review_image.image_id),
                "image_type": "review",
                "role": "review",
                "content_type": "image/png",
                "filename": review_image.image_name,
                "bytes": None,
                "review_image_id": review_image.image_id,
                "source_uri": (
                    f"mock-sc://review/{insp_time_str}/{wafer_key}/{defect_id}/"
                    f"{review_image.image_id}"
                ),
            }
        )

    images.append(
        {
            "image_id": f"{defect_id}_template",
            "image_type": "template",
            "role": "patch_template",
            "content_type": "image/png",
            "filename": "template.png",
            "bytes": None,
            "review_image_id": None,
            "source_uri": (
                f"mock-sc://patch/{insp_time_str}/{wafer_key}/{defect_id}/template.png"
            ),
        }
    )

    images.append(
        {
            "image_id": f"{defect_id}_defective",
            "image_type": "defective",
            "role": "patch_defective",
            "content_type": "image/png",
            "filename": "defective.png",
            "bytes": None,
            "review_image_id": None,
            "source_uri": (
                f"mock-sc://patch/{insp_time_str}/{wafer_key}/{defect_id}/defective.png"
            ),
        }
    )

    images.append(
        {
            "image_id": f"{defect_id}_difference",
            "image_type": "difference",
            "role": "patch_difference",
            "content_type": "image/png",
            "filename": "difference.png",
            "bytes": None,
            "review_image_id": None,
            "source_uri": (
                f"mock-sc://patch/{insp_time_str}/{wafer_key}/{defect_id}/difference.png"
            ),
        }
    )

    return images


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
        self._upstream = upstream_reader
        self._sparse_import_factory = sparse_import_factory
        self._import_batch_rows = import_batch_rows
        self._index_row_group_rows = index_row_group_rows

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
            inspection = await self._upstream.get_inspection(insp_dt, source_wafer_key)
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
                inspection=inspection,
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
        schema_columns = [
            ColumnSchema(name=c["name"], type=c["type"])
            for c in SC_SPARSE_SHARD_SCHEMA_V2
        ]
        pyarrow_schema = _build_v2_pyarrow_schema()

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
            session = operator.begin_columnar_import(
                schema_columns=schema_columns,
                schema_version="v2",
                index_row_group_rows=self._index_row_group_rows,
            )
            await session.finalize()
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
        session = operator.begin_columnar_import(
            schema_columns=schema_columns,
            schema_version="v2",
            index_row_group_rows=self._index_row_group_rows,
        )
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
                write_started = perf_counter()
                shard_entry = await session.append(table, row_id_column="sample_id")
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
            manifest_started = perf_counter()
            await session.finalize()
            manifest_seconds = perf_counter() - manifest_started
        except BaseException:
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
        inspection: Any | None,
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
        if inspection is not None:
            dataset_meta["geometry"] = _geometry_from_inspection(inspection)
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
