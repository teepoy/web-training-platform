from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, cast, overload

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

from app.modules.dataset_collections.domain.models import DatasetCollectionRevision
from app.modules.dataset_collections.port.local import (
    DatasetCollectionRevisionReaderPort,
)
from app.modules.sc.data_provider.cache import CachedDataObject, ScDataObjectCache
from app.modules.sc.data_provider.scope import ScDataScope
from app.modules.sc.domain.models import _coerce_naive_to_upstream_tz
from app.modules.sc.domain.upstream_reader import ScUpstreamReader
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.shared.domain.protocols import ArtifactStorage


_SAMPLE_COLUMN_DTYPES = {
    "row_key": pl.Utf8,
    "map_id": pl.Int32,
    "defect_id": pl.Int32,
    "sample_id": pl.Utf8,
    "source_dataset_id": pl.Utf8,
    "source_sample_id": pl.Utf8,
    "collection_member_id": pl.Utf8,
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
# Bump whenever the physical workbench identity contract changes.
_SAMPLES_BASE_FORMAT_VERSION = "v5-collection-row-key"
_REVIEW_IMAGES_FORMAT_VERSION = "v2-row-key"


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
        collection_revision_reader: DatasetCollectionRevisionReaderPort,
        artifact_storage: ArtifactStorage,
        cache: ScDataObjectCache,
        batch_rows: int,
    ) -> None:
        if batch_rows <= 0:
            raise ValueError("batch_rows must be greater than zero")
        self._upstream_reader = upstream_reader
        self._storage_factory = storage_factory
        self._collection_revision_reader = collection_revision_reader
        self._artifact_storage = artifact_storage
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
        if scope.kind == "dataset":
            return await self._materialize_dataset(scope, revision=revision)
        return await self._materialize_collection(scope, revision=revision)

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
                logical_key=(
                    f"{base_key}:review-images:{_REVIEW_IMAGES_FORMAT_VERSION}"
                ),
                scope=scope.cache_name,
                revision=0,
                revision_tracked=False,
                builder=lambda: _inspection_review_images_table(
                    review_task,
                    inspection_time=parsed_time.isoformat(),
                    wafer_key=wafer_key,
                ),
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
        dataset = await storage.get_dataset_metadata()
        inspection_time, wafer_key = _dataset_source_scope(dataset, scope.identity)
        sparse_task: asyncio.Task[pl.LazyFrame] | None = None

        async def load_sparse_lazyframe() -> pl.LazyFrame:
            nonlocal sparse_task
            if sparse_task is None:

                async def load() -> pl.LazyFrame:
                    return cast(
                        pl.LazyFrame,
                        await storage.list_samples(
                            return_lazyframe=True,
                            with_labels=False,
                            with_predictions=False,
                        ),
                    )

                sparse_task = asyncio.create_task(
                    load(), name=f"sc-dataset-samples-{scope.identity}"
                )
            return await sparse_task

        parsed_time = _parse_inspection_time(inspection_time)
        review_task: asyncio.Task[pl.DataFrame] | None = None

        async def load_review_images() -> pl.DataFrame:
            nonlocal review_task
            if review_task is None:
                review_task = asyncio.create_task(
                    self._load_review_images(parsed_time, wafer_key),
                    name=f"sc-review-images-{wafer_key}",
                )
            return await review_task

        async def build_review_images() -> pa.Table:
            sparse_lf = await load_sparse_lazyframe()
            review_df = await load_review_images()
            identities = _dataset_identities_lazyframe(
                sparse_lf,
                dataset_id=scope.identity,
            )
            return (
                await _review_images_with_row_keys(
                    review_df,
                    identities,
                    join_columns=["defect_id"],
                )
            ).to_arrow()

        async def build_samples_base(path: Path) -> None:
            sparse_lf = await load_sparse_lazyframe()
            review_df = await load_review_images()
            await _sink_lazyframe(
                _normalize_dataset_base_lazyframe(
                    sparse_lf,
                    review_df,
                    dataset_id=scope.identity,
                ),
                path,
            )

        review_images, base = await asyncio.gather(
            self._cache.get_or_build(
                logical_key=(
                    f"inspection:{inspection_time}/{wafer_key}:review-images:"
                    f"{_REVIEW_IMAGES_FORMAT_VERSION}"
                ),
                scope=scope.cache_name,
                revision=0,
                revision_tracked=False,
                builder=build_review_images,
            ),
            self._cache.get_or_build_file(
                logical_key=(
                    f"dataset:{scope.org_id}/{scope.identity}:samples-base:"
                    f"{_SAMPLES_BASE_FORMAT_VERSION}"
                ),
                scope=scope.cache_name,
                revision=0,
                revision_tracked=False,
                builder=build_samples_base,
            ),
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
                scope,
                annotation_lf,
                annotation_fingerprint,
                scope_revision=revision,
            ),
            self._materialize_prediction_overlay(
                scope,
                prediction_lf,
                prediction_fingerprint,
                scope_revision=revision,
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

    async def _materialize_collection(
        self, scope: ScDataScope, *, revision: int
    ) -> MaterializedScScope:
        collection_id, revision_id = scope.identity.rsplit("/", 1)
        collection_revision = await self._collection_revision_reader.get_revision(
            collection_id,
            revision_id,
            scope.org_id,
        )
        if (
            collection_revision.status != "ready"
            or not collection_revision.manifest_uri
        ):
            raise ValueError(
                f"Collection revision is not ready: {collection_id}/{revision_id}"
            )
        source_dataset_ids = _collection_source_dataset_ids(collection_revision)
        storages = dict(
            zip(
                source_dataset_ids,
                await asyncio.gather(
                    *(
                        self._storage_factory.open(dataset_id, scope.org_id)
                        for dataset_id in source_dataset_ids
                    )
                ),
                strict=True,
            )
        )
        artifact_task: asyncio.Task[Path] | None = None
        observed_source_task: asyncio.Task[pl.LazyFrame] | None = None
        reviews_task: asyncio.Task[pl.DataFrame] | None = None
        observed_resolution = collection_revision.source_resolution == "observed"

        with tempfile.TemporaryDirectory(prefix="sc-collection-workbench-") as tmp:
            artifact_path = Path(tmp) / "revision.parquet"

            async def load_artifact_path() -> Path:
                nonlocal artifact_task
                if artifact_task is None:

                    async def download() -> Path:
                        await self._artifact_storage.get_file(
                            cast(str, collection_revision.manifest_uri),
                            str(artifact_path),
                        )
                        return artifact_path

                    artifact_task = asyncio.create_task(
                        download(),
                        name=f"sc-collection-artifact-{revision_id}",
                    )
                return await artifact_task

            async def load_observed_source() -> pl.LazyFrame:
                nonlocal observed_source_task
                if observed_source_task is None:

                    async def load() -> pl.LazyFrame:
                        async def load_member(
                            dataset_id: str,
                            snapshot: dict[str, object],
                        ) -> pl.LazyFrame:
                            rows = cast(
                                pl.LazyFrame,
                                await storages[dataset_id].list_samples(
                                    return_lazyframe=True,
                                    with_labels=False,
                                    with_predictions=False,
                                ),
                            )
                            return _observed_collection_member_lazyframe(
                                rows,
                                dataset_id=dataset_id,
                                member_id=str(snapshot.get("member_id", "")),
                            )

                        member_frames = await asyncio.gather(
                            *(
                                load_member(dataset_id, snapshot)
                                for dataset_id, snapshot in zip(
                                    source_dataset_ids,
                                    collection_revision.source_snapshot,
                                    strict=True,
                                )
                            )
                        )
                        return pl.concat(member_frames, how="diagonal_relaxed")

                    observed_source_task = asyncio.create_task(
                        load(),
                        name=f"sc-collection-observed-source-{revision_id}",
                    )
                return await observed_source_task

            async def load_reviews() -> pl.DataFrame:
                nonlocal reviews_task
                if reviews_task is None:

                    async def load() -> pl.DataFrame:
                        frames: list[pl.DataFrame] = []
                        for dataset_id in source_dataset_ids:
                            dataset = await storages[dataset_id].get_dataset_metadata()
                            inspection_time, wafer_key = _dataset_source_scope(
                                dataset, dataset_id
                            )
                            frame = await self._load_review_images(
                                _parse_inspection_time(inspection_time), wafer_key
                            )
                            frames.append(
                                frame.with_columns(
                                    pl.lit(dataset_id).alias("source_dataset_id")
                                )
                            )
                        return pl.concat(frames, how="vertical_relaxed")

                    reviews_task = asyncio.create_task(
                        load(),
                        name=f"sc-collection-reviews-{revision_id}",
                    )
                return await reviews_task

            async def build_samples_base(path: Path) -> None:
                source = (
                    await load_observed_source()
                    if observed_resolution
                    else pl.scan_parquet(await load_artifact_path())
                )
                reviews = await load_reviews()
                await _sink_lazyframe(
                    _normalize_dataset_base_lazyframe(
                        source,
                        reviews,
                        assign_map_ids=True,
                    ),
                    path,
                )

            async def build_review_images() -> pa.Table:
                source = (
                    await load_observed_source()
                    if observed_resolution
                    else pl.scan_parquet(await load_artifact_path())
                )
                identities = source.select(
                    pl.col("source_dataset_id").cast(pl.Utf8),
                    pl.col("defect_id").cast(pl.Int32, strict=False),
                    pl.col("row_key").cast(pl.Utf8),
                )
                return (
                    await _review_images_with_row_keys(
                        await load_reviews(),
                        identities,
                        join_columns=["source_dataset_id", "defect_id"],
                    )
                ).to_arrow()

            base, review_images = await asyncio.gather(
                self._cache.get_or_build_file(
                    logical_key=(
                        f"collection:{scope.org_id}/{scope.identity}:samples-base:"
                        f"{_SAMPLES_BASE_FORMAT_VERSION}"
                    ),
                    scope=scope.cache_name,
                    revision=revision if observed_resolution else 0,
                    revision_tracked=observed_resolution,
                    builder=build_samples_base,
                ),
                self._cache.get_or_build(
                    logical_key=(
                        f"collection:{scope.org_id}/{scope.identity}:review-images:"
                        f"{_REVIEW_IMAGES_FORMAT_VERSION}"
                    ),
                    scope=scope.cache_name,
                    revision=revision if observed_resolution else 0,
                    revision_tracked=observed_resolution,
                    builder=build_review_images,
                ),
            )

        annotation_frames: list[pl.LazyFrame] = []
        prediction_frames: list[pl.LazyFrame] = []
        annotation_fingerprints: list[str] = []
        prediction_fingerprints: list[str] = []
        for dataset_id in source_dataset_ids:
            storage = cast(_MutableOverlayStorage, storages[dataset_id])
            (
                (annotation_lf, annotation_fingerprint),
                (
                    prediction_lf,
                    prediction_fingerprint,
                ),
            ) = await asyncio.gather(
                storage.annotation_overlay_lazyframe(),
                storage.prediction_overlay_lazyframe(),
            )
            annotation_fingerprints.append(f"{dataset_id}:{annotation_fingerprint}")
            prediction_fingerprints.append(f"{dataset_id}:{prediction_fingerprint}")
            if annotation_lf is not None:
                annotation_frames.append(
                    _prefix_overlay_sample_ids(
                        cast(pl.LazyFrame, annotation_lf), dataset_id
                    )
                )
            if prediction_lf is not None:
                prediction_frames.append(
                    _prefix_overlay_sample_ids(
                        cast(pl.LazyFrame, prediction_lf), dataset_id
                    )
                )

        annotation_overlay, prediction_overlay = await asyncio.gather(
            self._materialize_annotation_overlay(
                scope,
                pl.concat(annotation_frames, how="vertical_relaxed")
                if annotation_frames
                else None,
                _combined_fingerprint(annotation_fingerprints),
                scope_revision=revision,
            ),
            self._materialize_prediction_overlay(
                scope,
                pl.concat(prediction_frames, how="vertical_relaxed")
                if prediction_frames
                else None,
                _combined_fingerprint(prediction_fingerprints),
                scope_revision=revision,
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

    async def source_dataset_ids(self, scope: ScDataScope) -> tuple[str, ...]:
        if scope.kind == "dataset":
            return (scope.identity,)
        if scope.kind != "collection":
            return ()
        collection_id, revision_id = scope.identity.rsplit("/", 1)
        revision = await self._collection_revision_reader.get_revision(
            collection_id, revision_id, scope.org_id
        )
        return _collection_source_dataset_ids(revision)

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
                ).with_columns(
                    pl.concat_str(
                        [
                            pl.lit(parsed_time.isoformat()),
                            pl.lit(str(wafer_key)),
                            pl.col("defect_id").cast(pl.Utf8),
                        ],
                        separator="::",
                    ).alias("row_key")
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
        *,
        scope_revision: int,
    ) -> CachedDataObject | None:
        if lazyframe is None:
            return None
        overlay = cast(pl.LazyFrame, lazyframe).select(
            pl.col("sample_id").cast(pl.Utf8).alias("row_key"),
            pl.col("label").cast(pl.Utf8).alias("annotation_label"),
        )
        return await self._cache.get_or_build_file(
            logical_key=f"dataset:{scope.org_id}/{scope.identity}:annotations",
            scope=scope.cache_name,
            revision=_fingerprint_revision(fingerprint),
            scope_revision=scope_revision,
            builder=lambda path: _sink_lazyframe(overlay, path),
        )

    async def _materialize_prediction_overlay(
        self,
        scope: ScDataScope,
        lazyframe: Any | None,
        fingerprint: str,
        *,
        scope_revision: int,
    ) -> CachedDataObject | None:
        if lazyframe is None:
            return None
        overlay = cast(pl.LazyFrame, lazyframe).select(
            pl.col("sample_id").cast(pl.Utf8).alias("row_key"),
            pl.col("predicted_label").cast(pl.Utf8).alias("prediction_label"),
            pl.col("confidence")
            .cast(pl.Float64, strict=False)
            .alias("prediction_confidence"),
        )
        return await self._cache.get_or_build_file(
            logical_key=f"dataset:{scope.org_id}/{scope.identity}:predictions",
            scope=scope.cache_name,
            revision=_fingerprint_revision(fingerprint),
            scope_revision=scope_revision,
            builder=lambda path: _sink_lazyframe(overlay, path),
        )


def _dataset_source_scope(dataset: Any, dataset_id: str) -> tuple[str, int]:
    if dataset is None:
        raise ValueError(f"Dataset not found: {dataset_id}")
    metadata = getattr(dataset, "dataset_meta", None)
    if not isinstance(metadata, Mapping):
        raise ValueError(
            f"SC dataset {dataset_id} is missing dataset_meta source identity"
        )
    raw_inspection_time = metadata.get("source_inspection_time")
    if not isinstance(raw_inspection_time, str) or not raw_inspection_time.strip():
        raise ValueError(
            f"SC dataset {dataset_id} is missing dataset_meta.source_inspection_time"
        )
    try:
        inspection_time = _parse_inspection_time(raw_inspection_time)
    except ValueError as exc:
        raise ValueError(
            f"SC dataset {dataset_id} has invalid dataset_meta.source_inspection_time"
        ) from exc
    raw_wafer_key = metadata.get("source_wafer_key")
    if not isinstance(raw_wafer_key, int) or isinstance(raw_wafer_key, bool):
        raise ValueError(
            f"SC dataset {dataset_id} has invalid dataset_meta.source_wafer_key"
        )
    return inspection_time.isoformat(), raw_wafer_key


def _parse_inspection_time(value: str) -> datetime:
    return _coerce_naive_to_upstream_tz(
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    )


async def _inspection_review_images_table(
    review_task: Awaitable[pl.DataFrame],
    *,
    inspection_time: str,
    wafer_key: int,
) -> pa.Table:
    review_df = await review_task
    return review_df.with_columns(
        pl.concat_str(
            [
                pl.lit(inspection_time),
                pl.lit(str(wafer_key)),
                pl.col("defect_id").cast(pl.Utf8),
            ],
            separator="::",
        ).alias("row_key")
    ).to_arrow()


async def _review_images_with_row_keys(
    review_df: pl.DataFrame,
    identities: pl.LazyFrame,
    *,
    join_columns: list[str],
) -> pl.DataFrame:
    return await (
        review_df.lazy()
        .join(identities.unique(), on=join_columns, how="inner")
        .collect_async()
    )


def _dataset_identities_lazyframe(
    sparse_lf: pl.LazyFrame, *, dataset_id: str
) -> pl.LazyFrame:
    names = set(sparse_lf.collect_schema().names())
    row_key = (
        pl.col("sample_id").cast(pl.Utf8)
        if "sample_id" in names
        else pl.concat_str(
            [pl.lit(dataset_id), pl.col("defect_id").cast(pl.Utf8)],
            separator="::",
        )
    )
    return sparse_lf.select(
        pl.col("defect_id").cast(pl.Int32, strict=False),
        row_key.alias("row_key"),
    )


def _collection_source_dataset_ids(
    revision: DatasetCollectionRevision,
) -> tuple[str, ...]:
    dataset_ids = tuple(
        str(item.get("source_dataset_id", "")) for item in revision.source_snapshot
    )
    if not dataset_ids or any(not dataset_id for dataset_id in dataset_ids):
        raise ValueError(
            f"Collection revision {revision.id} has no valid source dataset snapshot"
        )
    if len(dataset_ids) != len(set(dataset_ids)):
        raise ValueError(
            f"Collection revision {revision.id} contains duplicate source datasets"
        )
    return dataset_ids


def _prefix_overlay_sample_ids(
    lazyframe: pl.LazyFrame, dataset_id: str
) -> pl.LazyFrame:
    return lazyframe.with_columns(
        pl.concat_str(
            [pl.lit(dataset_id), pl.col("sample_id").cast(pl.Utf8)],
            separator="::",
        ).alias("sample_id")
    )


def _observed_collection_member_lazyframe(
    rows: pl.LazyFrame,
    *,
    dataset_id: str,
    member_id: str,
) -> pl.LazyFrame:
    names = set(rows.collect_schema().names())
    if "sample_id" not in names:
        raise ValueError(f"Dataset '{dataset_id}' does not expose sample_id")
    source_sample = pl.col("sample_id").cast(pl.Utf8)
    row_key = pl.concat_str([pl.lit(dataset_id), source_sample], separator="::")
    return rows.with_columns(
        source_sample.alias("source_sample_id"),
        pl.lit(dataset_id).alias("source_dataset_id"),
        pl.lit(member_id).alias("collection_member_id"),
        row_key.alias("row_key"),
    ).with_columns(pl.col("row_key").alias("sample_id"))


def _combined_fingerprint(parts: list[str]) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


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


def _review_aggregate(
    review_df: pl.DataFrame,
    *,
    group_columns: list[str] | None = None,
) -> pl.DataFrame:
    groups = group_columns or ["defect_id"]
    if review_df.is_empty():
        schema: dict[str, pl.Series] = {
            "images": pl.Series([], dtype=pl.Int32),
            "review_image_ids_json": pl.Series([], dtype=pl.Utf8),
        }
        for group in groups:
            schema[group] = pl.Series(
                [], dtype=pl.Int32 if group == "defect_id" else pl.Utf8
            )
        return pl.DataFrame(schema)
    return review_df.group_by(groups).agg(
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
    *,
    dataset_id: str = "",
    assign_map_ids: bool = False,
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
        pl.col("defect_id").cast(pl.Int32, strict=False),
        (
            pl.col("sample_id").cast(pl.Utf8)
            if "sample_id" in schema_names
            else pl.concat_str(
                [pl.lit(dataset_id), pl.col("defect_id").cast(pl.Utf8)],
                separator="::",
            )
        ).alias("row_key"),
    )
    if assign_map_ids:
        # Freeze the numeric map dictionary in revision-artifact order before
        # joins, whose execution strategy is allowed to reorder output rows.
        base = base.with_row_index("map_id").with_columns(
            pl.col("map_id").cast(pl.Int32, strict=False)
        )
    join_columns = (
        ["source_dataset_id", "defect_id"]
        if "source_dataset_id" in schema_names
        and "source_dataset_id" in review_df.columns
        else ["defect_id"]
    )
    base = base.join(
        _review_aggregate(review_df, group_columns=join_columns).lazy(),
        on=join_columns,
        how="left",
    )
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
        elif column == "map_id":
            expressions.append(
                pl.col("defect_id").cast(dtype, strict=False).alias(column)
            )
        elif column == "source_dataset_id" and dataset_id:
            expressions.append(pl.lit(dataset_id).cast(dtype).alias(column))
        elif column == "source_sample_id" and "sample_id" in available:
            expressions.append(
                pl.col("sample_id").cast(dtype, strict=False).alias(column)
            )
        else:
            expressions.append(pl.lit(None).cast(dtype).alias(column))
    return base.with_columns(expressions)


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
        elif column == "map_id":
            expressions.append(
                pl.col("defect_id").cast(dtype, strict=False).alias(column)
            )
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
