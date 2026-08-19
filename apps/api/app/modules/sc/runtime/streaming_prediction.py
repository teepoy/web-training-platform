from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence

import polars as pl

from app.modules.sc.domain.job_image_source import (
    ScPatchImageBatchResolver,
    normalize_role_paths,
)


_REQUIRED_COLUMNS = {"sample_id"}
_LOCATOR_COLUMNS = (
    "inspection_time",
    "wafer_key",
    "defect_id",
    "role_paths",
)


async def stream_sc_prediction_image_pairs(
    rows: pl.LazyFrame,
    *,
    image_resolver: ScPatchImageBatchResolver,
    image_source_formats: Mapping[str, str],
    direct_dataset_id: str | None,
    input_batch_rows: int,
    roles: Sequence[str] = ("patch_defective", "patch_template"),
) -> AsyncIterator[dict[str, object]]:
    """Resolve paired SC images while bounding resident input to one row batch."""

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
    if direct_dataset_id is None and "source_dataset_id" not in schema_names:
        raise ValueError("Collection prediction source must expose source_dataset_id")

    columns = ["sample_id"]
    columns.extend(column for column in _LOCATOR_COLUMNS if column in schema_names)
    if "source_dataset_id" in schema_names:
        columns.append("source_dataset_id")
    batches = rows.select(columns).collect_batches(
        chunk_size=input_batch_rows,
        maintain_order=True,
        engine="streaming",
    )
    try:
        batch_number = 0
        while True:
            batch = await asyncio.to_thread(_next_batch, batches)
            if batch is None:
                break
            resolved = await _resolve_batch(
                batch,
                batch_number=batch_number,
                image_resolver=image_resolver,
                image_source_formats=image_source_formats,
                direct_dataset_id=direct_dataset_id,
                roles=roles,
            )
            for item in resolved:
                yield item
            batch_number += 1
    finally:
        close = getattr(batches, "close", None)
        if close is not None:
            await asyncio.to_thread(close)


async def _resolve_batch(
    batch: pl.DataFrame,
    *,
    batch_number: int,
    image_resolver: ScPatchImageBatchResolver,
    image_source_formats: Mapping[str, str],
    direct_dataset_id: str | None,
    roles: Sequence[str],
) -> list[dict[str, object]]:
    rows = list(batch.iter_rows(named=True))
    requests_by_format: dict[str, list[dict[str, object]]] = {}
    ordered: list[tuple[str, str]] = []
    for row_index, row in enumerate(rows):
        sample_id = str(row.get("sample_id") or "")
        dataset_id = str(row.get("source_dataset_id") or direct_dataset_id or "")
        if not sample_id:
            raise ValueError("SC prediction source contains an empty sample_id")
        if not dataset_id:
            raise ValueError(
                f"SC prediction sample '{sample_id}' has no source Dataset identity"
            )
        try:
            source_format = image_source_formats[dataset_id]
        except KeyError as exc:
            raise ValueError(
                f"SC prediction source Dataset '{dataset_id}' has no image source format"
            ) from exc
        request_id = f"{batch_number}:{row_index}"
        request = {
            "request_id": request_id,
            "sample_id": sample_id,
            "inspection_time": str(row.get("inspection_time") or ""),
            "wafer_key": int(row.get("wafer_key") or 0),
            "defect_id": str(row.get("defect_id") or ""),
            "role_paths": normalize_role_paths(row.get("role_paths")),
        }
        requests_by_format.setdefault(source_format, []).append(request)
        ordered.append((source_format, request_id))

    async def resolve_format(
        source_format: str,
        requests: list[dict[str, object]],
    ) -> tuple[str, dict[str, dict[str, dict[str, object]]]]:
        by_request: dict[str, dict[str, dict[str, object]]] = {
            str(request["request_id"]): {} for request in requests
        }
        async for result in image_resolver.resolve_patch_images(
            source_format=source_format,
            roles=list(roles),
            items=requests,
        ):
            request_id = str(result.get("request_id") or "")
            role = str(result.get("role") or "")
            if request_id not in by_request:
                raise RuntimeError(
                    f"Job image resolver returned unknown request_id {request_id!r}"
                )
            if role not in roles:
                raise RuntimeError(f"Job image resolver returned unknown role {role!r}")
            if role in by_request[request_id]:
                raise RuntimeError(
                    f"Job image resolver returned duplicate role {role!r} for "
                    f"request_id {request_id!r}"
                )
            by_request[request_id][role] = result
        return source_format, by_request

    format_results = dict(
        await asyncio.gather(
            *(
                resolve_format(source_format, requests)
                for source_format, requests in requests_by_format.items()
            )
        )
    )

    output: list[dict[str, object]] = []
    row_by_request = {
        f"{batch_number}:{row_index}": row for row_index, row in enumerate(rows)
    }
    for source_format, request_id in ordered:
        role_results = format_results[source_format][request_id]
        missing_roles = [role for role in roles if role not in role_results]
        row = row_by_request[request_id]
        sample_id = str(row["sample_id"])
        if missing_roles:
            raise RuntimeError(
                f"Job image resolver ended before resolving sample '{sample_id}' roles: "
                + ", ".join(missing_roles)
            )
        errors = [
            f"{role}: {role_results[role].get('error')}"
            for role in roles
            if role_results[role].get("error")
        ]
        item: dict[str, object] = {"sample_id": sample_id}
        if errors:
            item["error"] = "image resolution failed: " + "; ".join(errors)
        else:
            for role in roles:
                raw_image = role_results[role].get("image_data")
                if not isinstance(raw_image, (bytes, bytearray, memoryview)):
                    raise RuntimeError(
                        f"Job image resolver returned invalid bytes for sample "
                        f"'{sample_id}' role {role!r}"
                    )
                item[f"{role}_bytes"] = bytes(raw_image)
        output.append(item)
    return output


def _next_batch(batches: Iterator[pl.DataFrame]) -> pl.DataFrame | None:
    try:
        return next(batches)
    except StopIteration:
        return None


__all__ = ["stream_sc_prediction_image_pairs"]
