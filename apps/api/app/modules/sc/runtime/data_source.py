from __future__ import annotations

import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
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
from app.shared.db.models.datasets import DatasetORM


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
        async with app_context.shared.session_factory() as session:
            row = await session.get(DatasetORM, source.dataset_id)
            if row is None:
                raise ValueError(f"Dataset not found: {source.dataset_id}")
            requested_org = getattr(runtime_ctx, "org_id", "")
            if requested_org and row.org_id != requested_org and not row.is_public:
                raise ValueError(f"Dataset not found: {source.dataset_id}")
            dataset_meta = (
                dict(row.dataset_meta) if isinstance(row.dataset_meta, dict) else {}
            )
            dataset_org_id = row.org_id
            dataset_type = row.dataset_type
            view_types = tuple(cast(list[str], row.view_types))
        storage_factory = app_context.injector.get(DatasetStorageFactoryPort)
        storage = await storage_factory.open(source.dataset_id, org_id=dataset_org_id)
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
            label_space=tuple(
                str(label)
                for label in cast(list[object], dataset_meta.get("label_space", []))
            ),
            view_types=view_types,
            dataset_type=dataset_type,
            dataset_id=source.dataset_id,
            collection_id=None,
            collection_revision_id=None,
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
    with tempfile.TemporaryDirectory(prefix="sc-collection-runtime-") as tmp:
        data_path = Path(tmp) / "data.parquet"
        await app_context.shared.artifact_storage.get_file(
            revision.manifest_uri,
            str(data_path),
        )
        rows = pl.scan_parquet(data_path)
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
        )


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
        existing = set(columns)
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
