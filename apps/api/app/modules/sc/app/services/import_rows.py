from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from app.modules.sc.domain.models import (
    PatchSample,
    ScInspectionRecord,
    parse_inspection_time,
)


def iter_patch_samples_from_upstream_chunk(chunk: Any) -> Iterator[PatchSample | Any]:
    """Yield PatchSample-like rows from an upstream stream chunk.

    The SC upstream Protocol now streams Polars DataFrame batches for bulk paths,
    while older tests and small fake adapters may still yield one PatchSample at a
    time.  Keep both shapes accepted at this boundary and normalize DataFrame rows
    before import storage writes.
    """
    if isinstance(chunk, PatchSample):
        yield chunk
        return

    if hasattr(chunk, "to_dicts"):
        for row in chunk.to_dicts():
            yield _patch_sample_from_row(row)
        return

    if isinstance(chunk, dict):
        yield _patch_sample_from_row(chunk)
        return

    yield chunk


def _patch_sample_from_row(row: dict[str, Any]) -> PatchSample:
    defect_id = str(_required(row, "defect_id"))
    return PatchSample(
        sample_id=str(row.get("sample_id") or defect_id),
        inspection_time=parse_inspection_time(_required(row, "inspection_time")),
        wafer_key=_required_int(row, "wafer_key"),
        defect_id=defect_id,
        lot_id=str(_required(row, "lot_id")),
        wafer_x=_required_int(row, "wafer_x"),
        wafer_y=_required_int(row, "wafer_y"),
        die_x=_required_int(row, "die_x", fallback_key="index_x"),
        die_y=_required_int(row, "die_y", fallback_key="index_y"),
        rough_bin=_required_int(row, "rough_bin"),
        class_number=_optional_int(row.get("class_number")),
    )


def _required(row: dict[str, Any], key: str) -> Any:
    value = row[key]
    if value is None:
        raise ValueError(f"SC import row field {key!r} is required")
    return value


def _required_int(
    row: dict[str, Any], key: str, *, fallback_key: str | None = None
) -> int:
    if key in row and row[key] is not None:
        return int(row[key])
    if (
        fallback_key is not None
        and fallback_key in row
        and row[fallback_key] is not None
    ):
        return int(row[fallback_key])
    raise KeyError(key)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _geometry_from_inspection(record: ScInspectionRecord) -> dict:
    return {
        "center_x": record.center_x,
        "center_y": record.center_y,
        "origin_x": record.origin_x,
        "origin_y": record.origin_y,
        "die_size_x": record.die_size_x,
        "die_size_y": record.die_size_y,
        "origin_index_x": record.origin_index_x,
        "origin_index_y": record.origin_index_y,
        "wafer_id": record.wafer_id,
        "lot_id": record.lot_id,
        "device": record.device,
    }
