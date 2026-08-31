from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, cast

import polars as pl
import pyarrow.parquet as pq

from app.modules.sc.domain.models import _coerce_naive_to_upstream_tz
from app.modules.sc.domain.upstream_reader import ScUpstreamReader


_PLATFORM_MEMBERSHIP_COLUMNS = (
    "sample_id",
    "source_sample_id",
    "source_dataset_id",
    "collection_member_id",
    "row_key",
    "label",
    "annotation_id",
    "annotation_label",
    "predicted_label",
    "prediction_id",
    "prediction_label",
    "confidence",
    "prediction_confidence",
    "final_class",
)


def sc_dataset_source_identity(dataset: Any, dataset_id: str) -> tuple[datetime, int]:
    metadata = getattr(dataset, "dataset_meta", None)
    if not isinstance(metadata, Mapping):
        raise ValueError(f"SC dataset {dataset_id} is missing source identity metadata")
    raw_time = metadata.get("source_inspection_time")
    if not isinstance(raw_time, str) or not raw_time.strip():
        raise ValueError(f"SC dataset {dataset_id} is missing source_inspection_time")
    try:
        inspection_time = _coerce_naive_to_upstream_tz(
            datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        )
    except ValueError as exc:
        raise ValueError(
            f"SC dataset {dataset_id} has invalid source_inspection_time"
        ) from exc
    raw_wafer_key = metadata.get("source_wafer_key")
    if not isinstance(raw_wafer_key, int) or isinstance(raw_wafer_key, bool):
        raise ValueError(f"SC dataset {dataset_id} has invalid source_wafer_key")
    return inspection_time, raw_wafer_key


@asynccontextmanager
async def open_latest_sc_source(
    *,
    upstream_reader: ScUpstreamReader,
    membership: pl.LazyFrame,
    inspection_time: datetime,
    wafer_key: int,
    dataset_id: str,
    batch_rows: int,
    projection: Sequence[str] | None = None,
) -> AsyncIterator[pl.LazyFrame]:
    """Open a bounded, temporary latest-source view for Dataset membership."""
    if batch_rows <= 0:
        raise ValueError("batch_rows must be greater than zero")
    membership_names = set(membership.collect_schema().names())
    if "defect_id" not in membership_names:
        raise ValueError(f"SC dataset {dataset_id} does not expose defect_id")
    preserved_columns = [
        column
        for column in (*_PLATFORM_MEMBERSHIP_COLUMNS, "defect_id")
        if column in membership_names
    ]
    selected_membership = membership.select(
        *(pl.col(column).cast(pl.Utf8) for column in preserved_columns)
    )
    source_projection = None
    if projection is not None:
        source_projection = list(dict.fromkeys(("defect_id", *projection)))
    with tempfile.TemporaryDirectory(prefix="sc-latest-source-") as directory:
        workspace = Path(directory)
        output_path = workspace / "resolved.parquet"
        identity_index = sqlite3.connect(
            workspace / "membership.sqlite3", check_same_thread=False
        )
        writer: pq.ParquetWriter | None = None
        membership_batches = selected_membership.collect_batches(
            chunk_size=batch_rows,
            maintain_order=True,
            engine="streaming",
        )
        try:
            identity_index.execute(
                "CREATE TABLE membership (defect_id INTEGER PRIMARY KEY)"
            )
            while True:
                identities = await asyncio.to_thread(
                    _next_membership_batch, membership_batches
                )
                if identities is None:
                    break
                defect_ids = _membership_defect_ids(identities, dataset_id=dataset_id)
                await asyncio.to_thread(
                    _record_membership_ids,
                    identity_index,
                    defect_ids,
                    dataset_id,
                )
                source_frames: list[pl.DataFrame] = []
                source_row_count = 0
                async for batch in upstream_reader.stream_membership_sample_batches(
                    inspection_time,
                    wafer_key,
                    defect_ids=defect_ids,
                    batch_rows=batch_rows,
                    projection=source_projection,
                ):
                    frame = cast(pl.DataFrame, pl.from_arrow(batch))
                    if "defect_id" not in frame.columns:
                        raise RuntimeError(
                            "SC upstream sample schema is missing defect_id"
                        )
                    source_row_count += frame.height
                    if source_row_count > len(defect_ids):
                        raise RuntimeError(
                            "SC upstream returned more rows than the requested "
                            "Dataset membership batch"
                        )
                    if not frame.is_empty():
                        source_frames.append(frame)
                resolved = _resolve_membership_batch(
                    identities=identities,
                    source_frames=source_frames,
                    preserved_columns=preserved_columns,
                    dataset_id=dataset_id,
                )
                table = resolved.to_arrow()
                if writer is None:
                    writer = pq.ParquetWriter(output_path, table.schema)
                elif table.schema != writer.schema:
                    table = table.cast(writer.schema)
                await asyncio.to_thread(writer.write_table, table)
            if writer is None:
                raise RuntimeError(
                    f"SC upstream returned no source rows for Dataset {dataset_id}"
                )
        finally:
            close_batches = getattr(membership_batches, "close", None)
            if callable(close_batches):
                with suppress(Exception):
                    close_batches()
            if writer is not None:
                await asyncio.to_thread(writer.close)
            identity_index.close()
        yield pl.scan_parquet(output_path)


def _next_membership_batch(
    batches: Iterator[pl.DataFrame],
) -> pl.DataFrame | None:
    try:
        return next(batches)
    except StopIteration:
        return None


def _membership_defect_ids(identities: pl.DataFrame, *, dataset_id: str) -> list[int]:
    if identities["defect_id"].null_count():
        raise ValueError(f"SC dataset {dataset_id} contains malformed defect_id")
    try:
        values = identities["defect_id"].cast(pl.Int64, strict=True).to_list()
    except (TypeError, ValueError, pl.exceptions.InvalidOperationError) as exc:
        raise ValueError(
            f"SC dataset {dataset_id} contains malformed defect_id"
        ) from exc
    return [int(value) for value in values]


def _record_membership_ids(
    identity_index: sqlite3.Connection,
    defect_ids: list[int],
    dataset_id: str,
) -> None:
    try:
        identity_index.executemany(
            "INSERT INTO membership (defect_id) VALUES (?)",
            ((defect_id,) for defect_id in defect_ids),
        )
        identity_index.commit()
    except sqlite3.IntegrityError as exc:
        raise ValueError(
            f"SC dataset {dataset_id} contains duplicate defect_id"
        ) from exc


def _resolve_membership_batch(
    *,
    identities: pl.DataFrame,
    source_frames: list[pl.DataFrame],
    preserved_columns: list[str],
    dataset_id: str,
) -> pl.DataFrame:
    if not source_frames:
        raise RuntimeError(
            f"SC upstream returned no source rows for Dataset {dataset_id}"
        )
    source = pl.concat(source_frames, how="diagonal_relaxed").with_columns(
        pl.col("defect_id").cast(pl.Utf8)
    )
    if source["defect_id"].null_count():
        raise RuntimeError("SC upstream returned malformed defect_id values")
    if source["defect_id"].n_unique() != source.height:
        raise RuntimeError("SC upstream returned duplicate defect_id values")
    collisions = set(preserved_columns).intersection(source.columns)
    collisions.discard("defect_id")
    if collisions:
        source = source.drop(sorted(collisions))
    resolved = identities.join(
        source, on="defect_id", how="inner", maintain_order="left"
    )
    if resolved.height != identities.height:
        matched = set(resolved["defect_id"].to_list())
        missing = [
            str(value)
            for value in identities["defect_id"].to_list()
            if value not in matched
        ]
        raise RuntimeError(
            f"SC upstream is missing {len(missing)} Dataset identities: {missing[:10]}"
        )
    return resolved
