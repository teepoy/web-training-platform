from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, cast, overload

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

from app.modules.sc.data_provider.cache import CachedDataObject, ScDataObjectCache
from app.modules.sc.data_provider.scope import ScDataScope
from app.modules.sc.domain.models import _coerce_naive_to_upstream_tz
from app.modules.sc.domain.upstream_reader import ScUpstreamReader
from app.modules.storage.port.local import DatasetStorageFactoryPort


_SAMPLE_COLUMN_DTYPES = {
    "defect_id": pl.Int32,
    "sample_id": pl.Utf8,
    "inspection_time": pl.Utf8,
    "wafer_key": pl.Int64,
    "wafer_x": pl.Int64,
    "wafer_y": pl.Int64,
    "die_x": pl.Int64,
    "die_y": pl.Int64,
    "rough_bin": pl.Int64,
    "class_number": pl.Int64,
    "images": pl.Int32,
    "test_id": pl.Int64,
    "index_x": pl.Int64,
    "index_y": pl.Int64,
    "adder": pl.Int64,
    "cluster_id": pl.Int64,
    "size_x": pl.Int64,
    "size_y": pl.Int64,
    "size_d": pl.Int64,
    "area": pl.Int64,
    "final_bin": pl.Int64,
    "manual_bin": pl.Int64,
    "kill_ratio": pl.Float64,
    "annotation_label": pl.Utf8,
    "prediction_label": pl.Utf8,
    "prediction_confidence": pl.Float64,
    "final_class": pl.Utf8,
    "review_image_ids_json": pl.Utf8,
}

_WORKBENCH_OWNED_SOURCE_COLUMNS = (
    "images",
    "review_image_ids_json",
    "annotation_label",
    "prediction_label",
    "prediction_confidence",
    "final_class",
)
_SAMPLES_BASE_FORMAT_VERSION = "v2-full-source-columns"


@dataclass(frozen=True)
class MaterializedScScope:
    scope: ScDataScope
    revision: int
    samples_base: CachedDataObject
    review_images: CachedDataObject
    annotation_overlay: CachedDataObject | None
    prediction_overlay: CachedDataObject | None

    @property
    def objects(self) -> list[CachedDataObject]:
        result = [self.samples_base, self.review_images]
        if self.annotation_overlay is not None:
            result.append(self.annotation_overlay)
        if self.prediction_overlay is not None:
            result.append(self.prediction_overlay)
        return result

    @property
    def cache_status(self) -> str:
        return (
            "hit"
            if all(item.cache_status.startswith("hit") for item in self.objects)
            else "miss"
        )


class _MutableOverlayStorage(Protocol):
    async def annotation_overlay_lazyframe(self) -> tuple[Any | None, str]: ...

    async def prediction_overlay_lazyframe(self) -> tuple[Any | None, str]: ...


class ScDataMaterializer:
    def __init__(
        self,
        *,
        upstream_reader: ScUpstreamReader,
        storage_factory: DatasetStorageFactoryPort,
        cache: ScDataObjectCache,
        batch_rows: int,
    ) -> None:
        if batch_rows <= 0:
            raise ValueError("batch_rows must be greater than zero")
        self._upstream_reader = upstream_reader
        self._storage_factory = storage_factory
        self._cache = cache
        self._batch_rows = batch_rows

    async def materialize(
        self, scope: ScDataScope, *, revision: int
    ) -> MaterializedScScope:
        if scope.kind == "inspection":
            inspection_time, raw_wafer_key = scope.identity.rsplit("/", 1)
            return await self._materialize_inspection(
                scope,
                inspection_time=inspection_time,
                wafer_key=int(raw_wafer_key),
                revision=revision,
            )
        return await self._materialize_dataset(scope, revision=revision)

    async def _materialize_inspection(
        self,
        scope: ScDataScope,
        *,
        inspection_time: str,
        wafer_key: int,
        revision: int,
    ) -> MaterializedScScope:
        parsed_time = _parse_inspection_time(inspection_time)
        inspection = await self._upstream_reader.get_inspection(parsed_time, wafer_key)
        if inspection is None:
            raise ValueError(f"Inspection not found: {inspection_time}/{wafer_key}")
        sample_count = await self._upstream_reader.get_sample_count(
            parsed_time, wafer_key
        )
        review_task = asyncio.create_task(
            self._load_review_images(parsed_time, wafer_key),
            name=f"sc-review-images-{wafer_key}",
        )
        base_key = f"inspection:{inspection_time}/{wafer_key}"
        samples, review_images = await asyncio.gather(
            self._cache.get_or_build_file(
                logical_key=f"{base_key}:samples-base:{_SAMPLES_BASE_FORMAT_VERSION}",
                scope=scope.cache_name,
                revision=0,
                revision_tracked=False,
                builder=lambda path: self._write_inspection_samples(
                    path,
                    parsed_time=parsed_time,
                    wafer_key=wafer_key,
                    sample_count=sample_count,
                    review_task=review_task,
                ),
            ),
            self._cache.get_or_build(
                logical_key=f"{base_key}:review-images",
                scope=scope.cache_name,
                revision=0,
                revision_tracked=False,
                builder=lambda: _review_images_table(review_task),
            ),
        )
        return MaterializedScScope(
            scope=scope,
            revision=revision,
            samples_base=samples,
            review_images=review_images,
            annotation_overlay=None,
            prediction_overlay=None,
        )

    async def _materialize_dataset(
        self, scope: ScDataScope, *, revision: int
    ) -> MaterializedScScope:
        storage = await self._storage_factory.open(scope.identity, scope.org_id)
        sparse_lf = cast(
            pl.LazyFrame,
            await storage.list_samples(
                return_lazyframe=True,
                with_labels=False,
                with_predictions=False,
            ),
        )
        meta = (
            await sparse_lf.select("inspection_time", "wafer_key")
            .drop_nulls()
            .head(1)
            .collect_async()
        ).to_dicts()
        if not meta:
            raise ValueError(f"SC dataset {scope.identity} has no inspection scope")
        inspection_time = _isoformat(meta[0]["inspection_time"])
        wafer_key = int(meta[0]["wafer_key"])
        parsed_time = _parse_inspection_time(inspection_time)
        review_df = await self._load_review_images(parsed_time, wafer_key)
        review_images = await self._cache.get_or_build(
            logical_key=f"inspection:{inspection_time}/{wafer_key}:review-images",
            scope=scope.cache_name,
            revision=0,
            revision_tracked=False,
            builder=lambda: asyncio.sleep(0, result=review_df.to_arrow()),
        )
        base_lf = _normalize_dataset_base_lazyframe(sparse_lf, review_df)
        base = await self._cache.get_or_build_file(
            logical_key=(
                f"dataset:{scope.org_id}/{scope.identity}:samples-base:"
                f"{_SAMPLES_BASE_FORMAT_VERSION}"
            ),
            scope=scope.cache_name,
            revision=0,
            revision_tracked=False,
            builder=lambda path: _sink_lazyframe(base_lf, path),
        )
        overlay_storage = cast(_MutableOverlayStorage, storage)
        (
            (annotation_lf, annotation_fingerprint),
            (
                prediction_lf,
                prediction_fingerprint,
            ),
        ) = await asyncio.gather(
            overlay_storage.annotation_overlay_lazyframe(),
            overlay_storage.prediction_overlay_lazyframe(),
        )
        annotation_overlay, prediction_overlay = await asyncio.gather(
            self._materialize_annotation_overlay(
                scope, annotation_lf, annotation_fingerprint
            ),
            self._materialize_prediction_overlay(
                scope, prediction_lf, prediction_fingerprint
            ),
        )
        return MaterializedScScope(
            scope=scope,
            revision=revision,
            samples_base=base,
            review_images=review_images,
            annotation_overlay=annotation_overlay,
            prediction_overlay=prediction_overlay,
        )

    async def _load_review_images(
        self, inspection_time: datetime, wafer_key: int
    ) -> pl.DataFrame:
        review_lf = await self._upstream_reader.list_review_images(
            inspection_time, wafer_key
        )
        if review_lf is None:
            raise RuntimeError("upstream returned no review-image table")
        review_df = await review_lf.collect_async()
        if review_df.is_empty() and "defect_id" not in review_df.columns:
            return pl.DataFrame(
                {
                    "defect_id": pl.Series([], dtype=pl.Int32),
                    "image_id": pl.Series([], dtype=pl.Int64),
                }
            )
        missing = {"defect_id", "image_id"} - set(review_df.columns)
        if missing:
            raise RuntimeError(
                f"upstream review-image table missing columns: {sorted(missing)}"
            )
        return review_df.with_columns(
            pl.col("defect_id").cast(pl.Int32, strict=False),
            pl.col("image_id").cast(pl.Int64, strict=False),
        )

    async def _write_inspection_samples(
        self,
        path: Path,
        *,
        parsed_time: datetime,
        wafer_key: int,
        sample_count: int,
        review_task: Awaitable[pl.DataFrame],
    ) -> None:
        aggregate = _review_aggregate(await review_task)
        writer: pq.ParquetWriter | None = None
        try:
            async for batch in self._upstream_reader.stream_sample_batches(
                parsed_time,
                wafer_key,
                offset=0,
                count=sample_count,
                batch_rows=self._batch_rows,
            ):
                frame = cast(pl.DataFrame, pl.from_arrow(batch))
                normalized = _normalize_samples_frame(
                    _attach_review_metadata(frame, aggregate)
                )
                table = normalized.to_arrow()
                if writer is None:
                    writer = pq.ParquetWriter(path, table.schema)
                await asyncio.to_thread(writer.write_table, table)
        finally:
            if writer is not None:
                await asyncio.to_thread(writer.close)
        if writer is None:
            await asyncio.to_thread(
                pq.write_table,
                _empty_samples_frame().to_arrow(),
                path,
            )

    async def _materialize_annotation_overlay(
        self,
        scope: ScDataScope,
        lazyframe: Any | None,
        fingerprint: str,
    ) -> CachedDataObject | None:
        if lazyframe is None:
            return None
        overlay = cast(pl.LazyFrame, lazyframe).select(
            pl.col("sample_id").cast(pl.Int32, strict=False).alias("defect_id"),
            pl.col("label").cast(pl.Utf8).alias("annotation_label"),
        )
        return await self._cache.get_or_build_file(
            logical_key=f"dataset:{scope.org_id}/{scope.identity}:annotations",
            scope=scope.cache_name,
            revision=_fingerprint_revision(fingerprint),
            revision_tracked=False,
            builder=lambda path: _sink_lazyframe(overlay, path),
        )

    async def _materialize_prediction_overlay(
        self,
        scope: ScDataScope,
        lazyframe: Any | None,
        fingerprint: str,
    ) -> CachedDataObject | None:
        if lazyframe is None:
            return None
        overlay = cast(pl.LazyFrame, lazyframe).select(
            pl.col("sample_id").cast(pl.Int32, strict=False).alias("defect_id"),
            pl.col("predicted_label").cast(pl.Utf8).alias("prediction_label"),
            pl.col("confidence")
            .cast(pl.Float64, strict=False)
            .alias("prediction_confidence"),
        )
        return await self._cache.get_or_build_file(
            logical_key=f"dataset:{scope.org_id}/{scope.identity}:predictions",
            scope=scope.cache_name,
            revision=_fingerprint_revision(fingerprint),
            revision_tracked=False,
            builder=lambda path: _sink_lazyframe(overlay, path),
        )


def _parse_inspection_time(value: str) -> datetime:
    return _coerce_naive_to_upstream_tz(
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    )


async def _review_images_table(
    review_task: Awaitable[pl.DataFrame],
) -> pa.Table:
    return (await review_task).to_arrow()


async def _sink_lazyframe(lazyframe: pl.LazyFrame, path: Path) -> None:
    await asyncio.to_thread(
        lazyframe.sink_parquet,
        path,
        compression="zstd",
        maintain_order=True,
    )


def _fingerprint_revision(fingerprint: str) -> int:
    if len(fingerprint) < 16:
        raise ValueError("overlay fingerprint must contain at least 16 hex digits")
    return int(fingerprint[:16], 16)


def _empty_samples_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            column: pl.Series(name=column, values=[], dtype=dtype)
            for column, dtype in _SAMPLE_COLUMN_DTYPES.items()
        }
    )


def _review_aggregate(review_df: pl.DataFrame) -> pl.DataFrame:
    if review_df.is_empty():
        return pl.DataFrame(
            {
                "defect_id": pl.Series([], dtype=pl.Int32),
                "images": pl.Series([], dtype=pl.Int32),
                "review_image_ids_json": pl.Series([], dtype=pl.Utf8),
            }
        )
    return review_df.group_by("defect_id").agg(
        pl.len().cast(pl.Int32).alias("images"),
        pl.col("image_id")
        .implode()
        .map_elements(lambda ids: json.dumps(list(ids)), return_dtype=pl.Utf8)
        .alias("review_image_ids_json"),
    )


def _attach_review_metadata(
    samples: pl.DataFrame,
    aggregate: pl.DataFrame,
) -> pl.DataFrame:
    samples = _rename_workbench_owned_source_columns(samples)
    return (
        samples.with_columns(pl.col("defect_id").cast(pl.Int32, strict=False))
        .join(aggregate, on="defect_id", how="left")
        .with_columns(
            pl.col("images").fill_null(0),
            pl.col("review_image_ids_json").fill_null("[]"),
        )
    )


def _normalize_dataset_base_lazyframe(
    sparse_lf: pl.LazyFrame,
    review_df: pl.DataFrame,
) -> pl.LazyFrame:
    sparse_schema = sparse_lf.collect_schema()
    schema_names = set(sparse_schema.names())
    if "defect_id" not in schema_names:
        raise ValueError("SC dataset rows must include defect_id")
    # V2's nested image structs may contain bytes and remain read-compatible,
    # but must not be copied into the SQL cache.  A v3 scalar upstream images
    # column is metadata and is retained as upstream_images.
    if "images" in schema_names and not _is_viewer_scalar_dtype(
        sparse_schema["images"]
    ):
        sparse_lf = sparse_lf.drop("images")
        schema_names.remove("images")
    base = _rename_workbench_owned_source_columns(sparse_lf).with_columns(
        pl.col("defect_id").cast(pl.Int32, strict=False)
    )
    base = base.join(_review_aggregate(review_df).lazy(), on="defect_id", how="left")
    available = set(base.collect_schema().names())
    expressions: list[pl.Expr] = []
    for column, dtype in _SAMPLE_COLUMN_DTYPES.items():
        if column in available:
            expression = pl.col(column).cast(dtype, strict=False)
            if column == "images":
                expression = expression.fill_null(0)
            elif column == "review_image_ids_json":
                expression = expression.fill_null("[]")
            expressions.append(expression.alias(column))
        elif column == "cluster_id" and "cluster" in available:
            expressions.append(
                pl.col("cluster").cast(dtype, strict=False).alias(column)
            )
        elif column == "images":
            expressions.append(pl.lit(0).cast(dtype).alias(column))
        elif column == "review_image_ids_json":
            expressions.append(pl.lit("[]").cast(dtype).alias(column))
        else:
            expressions.append(pl.lit(None).cast(dtype).alias(column))
    return base.with_columns(expressions)


def _isoformat(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _normalize_samples_frame(df: pl.DataFrame) -> pl.DataFrame:
    expressions: list[pl.Expr] = [pl.col("defect_id").cast(pl.Int32, strict=False)]
    for column, dtype in _SAMPLE_COLUMN_DTYPES.items():
        if column == "defect_id" or column in df.columns:
            continue
        if column == "cluster_id" and "cluster" in df.columns:
            expressions.append(
                pl.col("cluster").cast(dtype, strict=False).alias(column)
            )
        elif column == "images":
            expressions.append(pl.lit(0).cast(dtype).alias(column))
        elif column == "review_image_ids_json":
            expressions.append(pl.lit("[]").cast(dtype).alias(column))
        else:
            expressions.append(pl.lit(None).cast(dtype).alias(column))
    df = df.with_columns(expressions)
    return df.with_columns(
        pl.col(column).cast(dtype, strict=False)
        for column, dtype in _SAMPLE_COLUMN_DTYPES.items()
    )


@overload
def _rename_workbench_owned_source_columns(frame: pl.DataFrame) -> pl.DataFrame: ...


@overload
def _rename_workbench_owned_source_columns(frame: pl.LazyFrame) -> pl.LazyFrame: ...


def _rename_workbench_owned_source_columns(
    frame: pl.DataFrame | pl.LazyFrame,
) -> pl.DataFrame | pl.LazyFrame:
    """Retain source values that collide with computed workbench columns."""
    names = set(frame.collect_schema().names())
    renames: dict[str, str] = {}
    for column in _WORKBENCH_OWNED_SOURCE_COLUMNS:
        if column not in names:
            continue
        shadow = f"upstream_{column}"
        if shadow in names:
            raise ValueError(
                "SC source contains both a workbench-owned column and its "
                f"reserved shadow column: {column!r}, {shadow!r}"
            )
        renames[column] = shadow
    return frame.rename(renames) if renames else frame


def _is_viewer_scalar_dtype(dtype: pl.DataType) -> bool:
    return dtype.is_numeric() or dtype in {
        pl.Boolean,
        pl.String,
        pl.Date,
        pl.Datetime,
        pl.Time,
    }
