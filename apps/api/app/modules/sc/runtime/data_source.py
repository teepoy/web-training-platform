from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
import logging
from typing import cast

import polars as pl

from app.modules.dataset_collections.port.local import (
    DatasetCollectionRevisionReaderPort,
)
from app.modules.runtime.domain.context import (
    PredictionRuntimeContext,
    TrainingRuntimeContext,
)
from app.modules.sc.app.services.latest_source import (
    resolve_latest_sc_source,
    sc_dataset_source_identity,
)
from app.modules.sc.domain.upstream_reader import ScUpstreamReader
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.modules.storage.domain.storage_agg import DatasetStorageAgg
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
    upstream_reader = app_context.injector.get(ScUpstreamReader)
    batch_rows = app_context.shared.config.sc.pipeline.materialization_batch_rows
    if source.kind == "dataset":
        assert source.dataset_id is not None
        storage_factory = app_context.injector.get(DatasetStorageFactoryPort)
        storage = await storage_factory.open(
            source.dataset_id,
            org_id=getattr(runtime_ctx, "org_id", ""),
        )
        dataset = cast(Dataset, await storage.get_dataset_metadata())
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
        inspection_time, wafer_key = sc_dataset_source_identity(
            dataset, source.dataset_id
        )
        rows = await resolve_latest_sc_source(
            upstream_reader=upstream_reader,
            membership=rows,
            inspection_time=inspection_time,
            wafer_key=wafer_key,
            dataset_id=source.dataset_id,
            batch_rows=batch_rows,
        )
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
    selected_member_ids = getattr(runtime_ctx, "collection_member_ids", None)
    selected_members = tuple(
        item
        for item in revision.members
        if selected_member_ids is None or item.get("member_id") in selected_member_ids
    )
    if selected_member_ids is not None:
        found = {str(item.get("member_id")) for item in selected_members}
        missing = [
            member_id for member_id in selected_member_ids if member_id not in found
        ]
        if missing:
            raise ValueError(
                "Collection revision does not contain selected members: "
                + ", ".join(missing)
            )
    source_dataset_ids = tuple(
        str(item["source_dataset_id"])
        for item in selected_members
        if item.get("source_dataset_id") is not None
    )
    storage_factory = app_context.injector.get(DatasetStorageFactoryPort)
    storages = await asyncio.gather(
        *(storage_factory.open(dataset_id, org_id) for dataset_id in source_dataset_ids)
    )
    datasets = await asyncio.gather(
        *(storage.get_dataset_metadata() for storage in storages)
    )
    label_space = (
        tuple(cast(Dataset, datasets[0]).task_spec.label_space) if datasets else ()
    )
    # Import lazily so dataset compatibility registration cannot recurse
    # through the SC runtime router while this module is initializing.
    from app.modules.datasets.port.local import DatasetRevisionReaderPort

    frames = await asyncio.gather(
        *(
            _observed_member_rows(
                storage,
                dataset_id=dataset_id,
                member_id=str(member.get("member_id", "")),
                with_labels=with_labels,
                with_predictions=with_predictions,
                upstream_reader=upstream_reader,
                batch_rows=batch_rows,
            )
            for storage, dataset_id, member in zip(
                storages,
                source_dataset_ids,
                selected_members,
                strict=True,
            )
        )
    )
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
        "Resolved current Collection runtime source collection_revision=%s "
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
        resolved_dataset_revision_ids=resolved_revision_ids,
    )


async def _observed_member_rows(
    storage: DatasetStorageAgg,
    *,
    dataset_id: str,
    member_id: str,
    with_labels: bool,
    with_predictions: bool,
    upstream_reader: ScUpstreamReader,
    batch_rows: int,
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
    dataset = cast(Dataset, await storage.get_dataset_metadata())
    inspection_time, wafer_key = sc_dataset_source_identity(dataset, dataset_id)
    rows = await resolve_latest_sc_source(
        upstream_reader=upstream_reader,
        membership=rows,
        inspection_time=inspection_time,
        wafer_key=wafer_key,
        dataset_id=dataset_id,
        batch_rows=batch_rows,
    )
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
