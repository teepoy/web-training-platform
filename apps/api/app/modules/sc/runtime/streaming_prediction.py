from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Iterator, Sequence
from contextlib import suppress

import polars as pl

from app.modules.sc.domain.image_stream import ScImageStreamSession

_REQUIRED_COLUMNS = {"sample_id", "inspection_time", "wafer_key", "defect_id"}


async def stream_sc_prediction_image_pairs(
    rows: pl.LazyFrame,
    *,
    image_stream: ScImageStreamSession,
    input_batch_rows: int,
    roles: Sequence[str] = ("patch_defective", "patch_template"),
) -> AsyncGenerator[dict[str, object], None]:
    """Resolve ordered SC images through one semantic service stream."""

    if input_batch_rows <= 0:
        raise ValueError("input_batch_rows must be greater than zero")
    if not roles:
        raise ValueError("at least one prediction image role is required")
    schema_names = set(rows.collect_schema().names())
    missing = sorted(_REQUIRED_COLUMNS.difference(schema_names))
    if missing:
        raise ValueError(
            "SC prediction source is missing required columns: " + ", ".join(missing)
        )
    batches = rows.select(sorted(_REQUIRED_COLUMNS)).collect_batches(
        chunk_size=input_batch_rows,
        maintain_order=True,
        engine="streaming",
    )
    pending: asyncio.Task[list[dict[str, object]]] | None = None

    async def resolve(batch: pl.DataFrame) -> list[dict[str, object]]:
        requests = [dict(row) for row in batch.iter_rows(named=True)]
        resolved = await image_stream.resolve_images(roles=roles, items=requests)
        if len(resolved) != len(requests):
            raise RuntimeError(
                "image-parser returned an incomplete batch: "
                f"expected {len(requests)}, got {len(resolved)}"
            )
        return resolved

    try:
        batch = await asyncio.to_thread(_next_batch, batches)
        if batch is not None:
            pending = asyncio.create_task(resolve(batch))
        while pending is not None:
            resolved = await pending
            next_batch = await asyncio.to_thread(_next_batch, batches)
            pending = (
                asyncio.create_task(resolve(next_batch))
                if next_batch is not None
                else None
            )
            if pending is not None:
                # Give the next service request a chance to enter gRPC before
                # downstream CPU/GPU preprocessing consumes the current batch.
                await asyncio.sleep(0)
            for item in resolved:
                yield _flatten_sample(item, roles)
    finally:
        if pending is not None:
            pending.cancel()
            with suppress(asyncio.CancelledError):
                await pending
        close = getattr(batches, "close", None)
        if close is not None:
            await asyncio.to_thread(close)


def _flatten_sample(item: dict[str, object], roles: Sequence[str]) -> dict[str, object]:
    sample_id = str(item.get("sample_id") or "")
    sample_error = str(item.get("error") or "")
    raw_images = item.get("images")
    if not isinstance(raw_images, list):
        raise RuntimeError(
            f"image-parser returned invalid image results for sample {sample_id!r}"
        )
    by_role: dict[str, dict[str, object]] = {}
    for raw in raw_images:
        if not isinstance(raw, dict):
            raise RuntimeError("image-parser returned an invalid role result")
        role = str(raw.get("role") or "")
        if role not in roles:
            raise RuntimeError(f"image-parser returned unknown role {role!r}")
        if role in by_role:
            raise RuntimeError(
                f"image-parser returned duplicate role {role!r} for sample "
                f"{sample_id!r}"
            )
        by_role[role] = raw
    missing = [role for role in roles if role not in by_role]
    if missing:
        raise RuntimeError(
            f"image-parser ended before resolving sample {sample_id!r} roles: "
            + ", ".join(missing)
        )
    errors = [sample_error] if sample_error else []
    errors.extend(
        f"{role}: {by_role[role].get('error')}"
        for role in roles
        if by_role[role].get("error")
    )
    output: dict[str, object] = {"sample_id": sample_id}
    if errors:
        output["error"] = "image resolution failed: " + "; ".join(errors)
        return output
    for role in roles:
        raw_image = by_role[role].get("image_data")
        content_type = by_role[role].get("content_type")
        if not isinstance(raw_image, (bytes, bytearray, memoryview)):
            raise RuntimeError(
                f"image-parser returned invalid bytes for sample {sample_id!r} "
                f"role {role!r}"
            )
        if not isinstance(content_type, str) or not content_type.strip():
            raise RuntimeError(
                f"image-parser returned no content type for sample {sample_id!r} "
                f"role {role!r}"
            )
        output[f"{role}_bytes"] = bytes(raw_image)
        output[f"{role}_content_type"] = content_type.strip().lower()
    return output


def _next_batch(batches: Iterator[pl.DataFrame]) -> pl.DataFrame | None:
    try:
        return next(batches)
    except StopIteration:
        return None


__all__ = ["stream_sc_prediction_image_pairs"]
