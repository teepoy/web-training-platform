from __future__ import annotations

import asyncio
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
import logging
from pathlib import Path
from typing import cast

import polars as pl

from app.modules.dataset_collections.port.local import (
    DatasetCollectionRevisionReaderPort,
)
from app.modules.runtime.domain.context import (
    PredictionRuntimeContext,
    TrainingRuntimeContext,
)
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.modules.storage.domain.storage_agg import DatasetStorageAgg
from app.modules.sc.domain.image_source import require_sc_image_source_format
from app.shared.api.schemas import Dataset


_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ScRuntimeSource:
    rows: pl.LazyFrame
    source_identity: str
    label_space: tuple[str, ...]
    view_types: tuple[str, ...]
    dataset_type: str
    dataset_id: str | None
    collection_id: str | None
    collection_revision_id: str | None
    source_dataset_ids: tuple[str, ...]
    image_source_formats: dict[str, str]
    resolved_dataset_revision_ids: tuple[str, ...] = ()


@asynccontextmanager
async def open_sc_runtime_source(
    runtime_ctx: TrainingRuntimeContext | PredictionRuntimeContext,
    *,
    with_labels: bool,
    with_predictions: bool,
) -> AsyncIterator[ScRuntimeSource]:
    app_context = runtime_ctx.app_context
    if app_context.injector is None:
        raise RuntimeError("AppContext injector was not initialized")
    source = runtime_ctx.data_source
    if source.kind == "dataset":
        assert source.dataset_id is not None
        storage_factory = app_context.injector.get(DatasetStorageFactoryPort)
        storage = await storage_factory.open(
            source.dataset_id,
            org_id=getattr(runtime_ctx, "org_id", ""),
        )
        dataset = cast(Dataset, await storage.get_dataset_metadata())
        image_source_format = require_sc_image_source_format(dataset)
        rows = cast(
            pl.LazyFrame,
            await storage.list_samples(
                return_lazyframe=True,
                with_labels=with_labels,
                with_predictions=with_predictions,
                sample_ids=runtime_ctx.sample_ids,
            ),
        )
        rows = _normalize_storage_rows(rows)
        yield ScRuntimeSource(
            rows=rows,
            source_identity=source.identity,
            label_space=tuple(dataset.task_spec.label_space),
            view_types=tuple(dataset.view_types),
            dataset_type=dataset.dataset_type,
            dataset_id=source.dataset_id,
            collection_id=source.collection_id,
            collection_revision_id=source.collection_revision_id,
            source_dataset_ids=(source.dataset_id,),
            image_source_formats={source.dataset_id: image_source_format},
        )
        return

    assert source.collection_id is not None
    assert source.collection_revision_id is not None
    org_id = getattr(runtime_ctx, "org_id", "")
    if not org_id:
        raise ValueError("org_id is required for collection revision runtime input")
    reader = app_context.injector.get(DatasetCollectionRevisionReaderPort)
    revision = await reader.get_revision(
        source.collection_id,
        source.collection_revision_id,
        org_id,
    )
    if revision.status != "ready" or revision.manifest_uri is None:
        raise ValueError(f"Collection revision is not ready: {revision.id}")
    source_dataset_ids = tuple(
        str(item["source_dataset_id"])
        for item in revision.source_snapshot
        if item.get("source_dataset_id") is not None
    )
    first_snapshot = revision.source_snapshot[0] if revision.source_snapshot else {}
    raw_label_space = first_snapshot.get("label_space", [])
    label_space = (
        tuple(str(label) for label in raw_label_space)
        if isinstance(raw_label_space, list)
        else ()
    )
    if revision.source_resolution == "observed":
        # Import lazily so dataset compatibility registration cannot recurse
        # through the SC runtime router while this module is initializing.
        from app.modules.datasets.port.local import DatasetRevisionReaderPort

        storage_factory = app_context.injector.get(DatasetStorageFactoryPort)
        storages = await asyncio.gather(
            *(
                storage_factory.open(dataset_id, org_id)
                for dataset_id in source_dataset_ids
            )
        )
        frames = await asyncio.gather(
            *(
                _observed_member_rows(
                    storage,
                    dataset_id=dataset_id,
                    member_id=str(snapshot.get("member_id", "")),
                    with_labels=with_labels,
                    with_predictions=with_predictions,
                )
                for storage, dataset_id, snapshot in zip(
                    storages,
                    source_dataset_ids,
                    revision.source_snapshot,
                    strict=True,
                )
            )
        )
        member_datasets = await asyncio.gather(
            *(storage.get_dataset_metadata() for storage in storages)
        )
        image_source_formats = {
            dataset_id: require_sc_image_source_format(cast(Dataset, dataset))
            for dataset_id, dataset in zip(
                source_dataset_ids,
                member_datasets,
                strict=True,
            )
        }
        dataset_revision_reader = app_context.injector.get(DatasetRevisionReaderPort)
        launch_revisions = await asyncio.gather(
            *(
                dataset_revision_reader.resolve_or_create_baseline(
                    dataset_id=dataset_id,
                    org_id=org_id,
                    created_by=runtime_ctx.created_by,
                )
                for dataset_id in source_dataset_ids
            )
        )
        resolved_revision_ids = tuple(item.id for item in launch_revisions)
        _logger.info(
            "Resolved observed Collection runtime source collection_revision=%s "
            "dataset_revisions=%s reproducible=false",
            revision.id,
            resolved_revision_ids,
        )
        rows = pl.concat(frames, how="diagonal_relaxed")
        if runtime_ctx.sample_ids is not None:
            rows = rows.filter(pl.col("sample_id").is_in(runtime_ctx.sample_ids))
        yield ScRuntimeSource(
            rows=rows,
            source_identity=source.identity,
            label_space=label_space,
            view_types=(revision.target_view_id,),
            dataset_type="image_sc_collection",
            dataset_id=None,
            collection_id=source.collection_id,
            collection_revision_id=revision.id,
            source_dataset_ids=source_dataset_ids,
            image_source_formats=image_source_formats,
            resolved_dataset_revision_ids=resolved_revision_ids,
        )
        return

    with tempfile.TemporaryDirectory(prefix="sc-collection-runtime-") as tmp:
        data_path = Path(tmp) / "data.parquet"
        await app_context.shared.artifact_storage.get_file(
            revision.manifest_uri,
            str(data_path),
        )
        rows = pl.scan_parquet(data_path)
        if runtime_ctx.sample_ids is not None:
            rows = rows.filter(pl.col("sample_id").is_in(runtime_ctx.sample_ids))
        image_source_formats = _snapshot_image_source_formats(revision.source_snapshot)
        yield ScRuntimeSource(
            rows=rows,
            source_identity=source.identity,
            label_space=label_space,
            view_types=(revision.target_view_id,),
            dataset_type="image_sc_collection",
            dataset_id=None,
            collection_id=source.collection_id,
            collection_revision_id=revision.id,
            source_dataset_ids=source_dataset_ids,
            image_source_formats=image_source_formats,
        )


def _snapshot_image_source_formats(
    source_snapshot: tuple[dict[str, object], ...],
) -> dict[str, str]:
    formats: dict[str, str] = {}
    for item in source_snapshot:
        dataset_id = item.get("source_dataset_id")
        image_source = item.get("image_source")
        if not isinstance(dataset_id, str) or not dataset_id:
            raise ValueError("Collection source snapshot is missing source_dataset_id")
        if not isinstance(image_source, dict):
            raise ValueError(
                f"Collection member Dataset '{dataset_id}' has no observed image "
                "source binding"
            )
        contract = image_source.get("contract")
        source_format = image_source.get("format")
        if (
            contract != "filesystem.image-source.v1"
            or not isinstance(source_format, str)
            or not source_format.strip()
        ):
            raise ValueError(
                f"Collection member Dataset '{dataset_id}' has an incompatible "
                "image source binding"
            )
        formats[dataset_id] = source_format
    return formats


async def _observed_member_rows(
    storage: DatasetStorageAgg,
    *,
    dataset_id: str,
    member_id: str,
    with_labels: bool,
    with_predictions: bool,
) -> pl.LazyFrame:
    rows = cast(
        pl.LazyFrame,
        await storage.list_samples(
            return_lazyframe=True,
            with_labels=with_labels,
            with_predictions=with_predictions,
        ),
    )
    rows = _normalize_storage_rows(rows)
    if "sample_id" not in rows.collect_schema().names():
        raise ValueError(f"Dataset '{dataset_id}' does not expose sample_id")
    source_sample = pl.col("sample_id").cast(pl.String)
    row_key = pl.concat_str([pl.lit(dataset_id), source_sample], separator="::")
    return rows.with_columns(
        source_sample.alias("source_sample_id"),
        pl.lit(dataset_id).alias("source_dataset_id"),
        pl.lit(member_id).alias("collection_member_id"),
        row_key.alias("row_key"),
    ).with_columns(pl.col("row_key").alias("sample_id"))


def decode_collection_row_key(
    row_key: str,
    *,
    allowed_dataset_ids: tuple[str, ...],
) -> tuple[str, str]:
    dataset_id, separator, sample_id = row_key.partition("::")
    if not separator or not sample_id or dataset_id not in allowed_dataset_ids:
        raise ValueError(f"Invalid collection revision row key: {row_key!r}")
    return dataset_id, sample_id


def _normalize_storage_rows(rows: pl.LazyFrame) -> pl.LazyFrame:
    schema = rows.collect_schema()
    columns = schema.names()
    if "sample_id" in columns or "id" not in columns:
        return rows
    expressions: list[pl.Expr] = [pl.col("id").cast(pl.String).alias("sample_id")]
    expressions.extend(
        pl.col(column)
        for column in columns
        if column not in {"id", "dataset_id", "metadata_json"}
    )
    metadata_dtype = schema.get("metadata_json")
    if isinstance(metadata_dtype, pl.Struct):
        # The platform sample id is the runtime identity.  SC metadata can
        # carry a separate upstream ``sample_id``; do not project it over the
        # platform-owned alias and create duplicate LazyFrame columns.
        existing = set(columns) | {"sample_id"}
        expressions.extend(
            pl.col("metadata_json").struct.field(field.name).alias(field.name)
            for field in metadata_dtype.fields
            if field.name not in existing
        )
    return rows.select(expressions)


__all__ = [
    "ScRuntimeSource",
    "decode_collection_row_key",
    "open_sc_runtime_source",
]
