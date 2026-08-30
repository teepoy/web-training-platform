from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, cast

import polars as pl

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


async def resolve_latest_sc_source(
    *,
    upstream_reader: ScUpstreamReader,
    membership: pl.LazyFrame,
    inspection_time: datetime,
    wafer_key: int,
    dataset_id: str,
    batch_rows: int,
    projection: Sequence[str] | None = None,
) -> pl.LazyFrame:
    """Semi-join stable Dataset membership with authoritative current source rows."""
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
    identities = await membership.select(
        *(pl.col(column).cast(pl.Utf8) for column in preserved_columns)
    ).collect_async()
    if identities["defect_id"].null_count():
        raise ValueError(f"SC dataset {dataset_id} contains malformed defect_id")
    if identities["defect_id"].n_unique() != identities.height:
        raise ValueError(f"SC dataset {dataset_id} contains duplicate defect_id")

    source_projection = None
    if projection is not None:
        source_projection = list(dict.fromkeys(("defect_id", *projection)))
    try:
        membership_defect_ids = [
            int(value) for value in identities["defect_id"].to_list()
        ]
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"SC dataset {dataset_id} contains malformed defect_id"
        ) from exc
    frames: list[pl.DataFrame] = []
    async for batch in upstream_reader.stream_membership_sample_batches(
        inspection_time,
        wafer_key,
        defect_ids=membership_defect_ids,
        batch_rows=batch_rows,
        projection=source_projection,
    ):
        frame = cast(pl.DataFrame, pl.from_arrow(batch))
        if "defect_id" not in frame.columns:
            raise RuntimeError("SC upstream sample schema is missing defect_id")
        frames.append(frame)
    if not frames:
        raise RuntimeError(
            f"SC upstream returned no source rows for Dataset {dataset_id}"
        )
    source = pl.concat(frames, how="diagonal_relaxed").with_columns(
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
    resolved = identities.join(source, on="defect_id", how="inner")
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
    return resolved.lazy()
