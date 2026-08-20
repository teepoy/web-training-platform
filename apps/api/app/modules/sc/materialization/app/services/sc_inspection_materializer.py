from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import Iterator
from contextlib import ExitStack
from typing import Any

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

from app.modules.storage.domain.data_plane import (
    DataPlaneManifest,
    DataPlaneSchemaRegistry,
    DataPlaneShard,
)
from app.modules.sc.materialization.domain.sc_inspection import (
    DEFAULT_PATCH_IMAGE_TYPES,
    ScInspectionMaterialization,
)
from app.modules.sc.domain.image_stream import (
    ScImageStreamSession,
    ScTrainingImageStreamFactory,
)
from app.modules.sc.domain.models import parse_inspection_time
from app.modules.sc.schema import find_images_by_role
from app.modules.sc.app.services.training_images import (
    normalize_sc_training_row,
    readable_image_bytes,
)
from app.modules.sc.capabilities import SC_PATCH_IMAGE_V1


class ScMaterializationCapacityError(RuntimeError):
    """The configured materialized-output budget was exceeded."""


class ScInspectionMaterializer:
    def __init__(
        self,
        *,
        image_stream_factory: ScTrainingImageStreamFactory,
        schema_registry: DataPlaneSchemaRegistry,
        batch_rows: int,
        max_error_records: int,
        temp_dir: str | None = None,
    ) -> None:
        if batch_rows <= 0:
            raise ValueError("batch_rows must be greater than zero")
        if max_error_records <= 0:
            raise ValueError("max_error_records must be greater than zero")
        self._image_stream_factory = image_stream_factory
        self._schema_registry = schema_registry
        self._batch_rows = batch_rows
        self._max_error_records = max_error_records
        self._temp_dir = temp_dir

    async def materialize(
        self,
        *,
        rows_lazyframe: Any,
        dataset_id: str = "",
        job_id: str = "",
        image_types: list[str] | None = None,
        max_output_bytes: int,
    ) -> ScInspectionMaterialization:
        if max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be greater than zero")
        image_types = image_types or list(DEFAULT_PATCH_IMAGE_TYPES)
        schema = self._schema_registry.get(
            SC_PATCH_IMAGE_V1.contract,
            SC_PATCH_IMAGE_V1.schema_version,
        )
        requested_roles = {
            _materialized_column_name(image_type): _image_role(image_type)
            for image_type in image_types
        }
        errors: list[dict[str, str]] = []
        columns = [_materialized_column_name(t) for t in image_types]
        unsupported_columns = sorted(set(columns).difference(schema.names))
        if unsupported_columns:
            raise ValueError(
                f"{SC_PATCH_IMAGE_V1.view_id} does not declare requested materialized "
                f"columns: {', '.join(unsupported_columns)}"
            )
        with ExitStack() as cleanup:
            handle = tempfile.NamedTemporaryFile(
                suffix=".parquet", delete=False, dir=self._temp_dir
            )
            handle.close()
            cleanup.callback(_unlink_if_exists, handle.name)
            writer: pq.ParquetWriter | None = None
            row_count = 0
            logical_output_bytes = 0
            batches = rows_lazyframe.collect_batches(
                chunk_size=self._batch_rows,
                maintain_order=True,
                engine="streaming",
            )
            async with self._image_stream_factory.open() as image_stream:
                try:
                    while True:
                        batch = await asyncio.to_thread(_next_batch, batches)
                        if batch is None:
                            break
                        rows = [
                            normalize_sc_training_row(dict(raw_row))
                            for raw_row in batch.iter_rows(named=True)
                        ]
                        table = await self._materialize_batch(
                            rows,
                            image_stream=image_stream,
                            requested_roles=requested_roles,
                            image_types=image_types,
                            columns=columns,
                            errors=errors,
                            schema=schema,
                        )
                        logical_output_bytes += table.nbytes
                        if logical_output_bytes > max_output_bytes:
                            raise ScMaterializationCapacityError(
                                "SC materialization exceeded configured output budget: "
                                f"{logical_output_bytes} > {max_output_bytes} bytes"
                            )
                        if writer is None:
                            writer = pq.ParquetWriter(handle.name, schema)
                        await asyncio.to_thread(writer.write_table, table)
                        row_count += table.num_rows
                        if os.path.getsize(handle.name) > max_output_bytes:
                            raise ScMaterializationCapacityError(
                                "SC materialization Parquet exceeded configured output "
                                f"budget of {max_output_bytes} bytes"
                            )
                finally:
                    if writer is not None:
                        await asyncio.to_thread(writer.close)
            if writer is None:
                await asyncio.to_thread(
                    pq.write_table,
                    _rows_to_table([], schema=schema),
                    handle.name,
                )
            size_bytes = os.path.getsize(handle.name)
            if size_bytes > max_output_bytes:
                raise ScMaterializationCapacityError(
                    "SC materialization Parquet exceeded configured output budget: "
                    f"{size_bytes} > {max_output_bytes} bytes"
                )
            physical_schema = await asyncio.to_thread(pq.read_schema, handle.name)
            if not physical_schema.equals(schema):
                raise ValueError(
                    "SC materialization Parquet schema does not match "
                    f"{SC_PATCH_IMAGE_V1.view_id}: "
                    f"expected {schema}, got {physical_schema}"
                )
            manifest = DataPlaneManifest.from_schema(
                view_contract=SC_PATCH_IMAGE_V1.contract,
                view_schema_version=SC_PATCH_IMAGE_V1.schema_version,
                dataset_id=dataset_id,
                job_id=job_id,
                format="parquet",
                schema=schema,
                schema_ref=self._schema_registry.schema_ref(
                    SC_PATCH_IMAGE_V1.contract,
                    SC_PATCH_IMAGE_V1.schema_version,
                ),
                image_encoding="embedded_bytes",
                image_roles=tuple(image_types),
                label_columns=("label",),
                shards=(
                    DataPlaneShard(
                        uri=f"file://{handle.name}",
                        format="parquet",
                        row_count=row_count,
                        size_bytes=size_bytes,
                    ),
                ),
                row_count=row_count,
            )
            manifest.validate_transport()
            materialization = ScInspectionMaterialization(
                parquet_path=handle.name,
                row_count=row_count,
                manifest=manifest,
                errors=errors,
            )
            cleanup.pop_all()
            return materialization

    async def _materialize_batch(
        self,
        rows: list[dict[str, Any]],
        *,
        image_stream: ScImageStreamSession,
        requested_roles: dict[str, str],
        image_types: list[str],
        columns: list[str],
        errors: list[dict[str, str]],
        schema: pa.Schema,
    ) -> pa.Table:
        image_bytes: dict[tuple[int, str], bytes] = {}
        missing_requests: list[dict[str, object]] = []
        requested_by_id: dict[str, set[str]] = {}
        row_by_id: dict[str, int] = {}
        for row_index, row in enumerate(rows):
            inspection_time = str(row.get("inspection_time") or "")
            wafer_key = int(row.get("wafer_key", 0) or 0)
            defect_id = str(row.get("defect_id") or "")
            sample_id = str(row.get("sample_id") or "")
            if not sample_id:
                raise ValueError(
                    "SC materialization source contains an empty sample_id"
                )
            if sample_id in row_by_id:
                raise ValueError(
                    f"SC materialization source contains duplicate sample_id {sample_id!r}"
                )
            row_by_id[sample_id] = row_index
            images = row.get("images")
            if not isinstance(images, list):
                images = []
            missing_roles: list[str] = []
            for column, role in requested_roles.items():
                refs = find_images_by_role(images, role)
                raw = refs[0].get("bytes") if refs else None
                readable = readable_image_bytes(raw)
                if readable is None:
                    missing_roles.append(role)
                    continue
                image_bytes[(row_index, column)] = readable
            if not missing_roles:
                continue
            requested_by_id[sample_id] = set(missing_roles)
            missing_requests.append(
                {
                    "sample_id": sample_id,
                    "inspection_time": inspection_time,
                    "wafer_key": wafer_key,
                    "defect_id": defect_id,
                }
            )

        received: dict[str, set[str]] = {
            request_id: set() for request_id in requested_by_id
        }
        if missing_requests:
            resolved_items = await image_stream.resolve_images(
                roles=tuple(requested_roles.values()),
                items=missing_requests,
            )
            for item in resolved_items:
                sample_id = str(item.get("sample_id") or "")
                if sample_id not in requested_by_id:
                    raise RuntimeError(
                        f"image-parser returned unknown sample_id {sample_id!r}"
                    )
                item_error = str(item.get("error") or "")
                raw_images = item.get("images")
                if not isinstance(raw_images, list):
                    raise RuntimeError(
                        f"image-parser returned invalid images for sample {sample_id!r}"
                    )
                for raw_image in raw_images:
                    if not isinstance(raw_image, dict):
                        raise RuntimeError(
                            "image-parser returned an invalid role result"
                        )
                    role = str(raw_image.get("role") or "")
                    if role not in requested_by_id[sample_id]:
                        continue
                    if role in received[sample_id]:
                        raise RuntimeError(
                            f"image-parser returned duplicate role {role!r} for "
                            f"sample {sample_id!r}"
                        )
                    received[sample_id].add(role)
                    image_type = _materialized_column_name(role)
                    error = item_error or str(raw_image.get("error") or "")
                    defect_id = str(rows[row_by_id[sample_id]].get("defect_id") or "")
                    if error:
                        self._append_error(
                            errors,
                            {
                                "defect_id": defect_id,
                                "image_type": image_type,
                                "error": error,
                            },
                        )
                        continue
                    image_data = raw_image.get("image_data", b"")
                    if not isinstance(image_data, (bytes, bytearray, memoryview)):
                        raise RuntimeError(
                            "image-parser returned non-bytes image_data for "
                            f"sample {sample_id!r} role {role!r}"
                        )
                    image_bytes[(row_by_id[sample_id], image_type)] = bytes(image_data)

        for sample_id, expected_roles in requested_by_id.items():
            missing_roles = sorted(expected_roles.difference(received[sample_id]))
            for role in missing_roles:
                row_index = row_by_id[sample_id]
                self._append_error(
                    errors,
                    {
                        "defect_id": str(rows[row_index].get("defect_id") or ""),
                        "image_type": role,
                        "error": "image parser stream ended before resolving role",
                    },
                )

        materialized_rows: list[dict[str, Any]] = []
        for row_index, row in enumerate(rows):
            defect_id = str(row.get("defect_id", ""))
            wafer_key = int(row.get("wafer_key", 0) or 0)
            out = {
                "sample_id": str(row.get("sample_id", "")),
                "defect_id": defect_id,
                "inspection_time": _normalize_inspection_time(
                    row.get("inspection_time")
                ),
                "wafer_key": wafer_key,
                "wafer_x": _optional_int(row.get("wafer_x")),
                "wafer_y": _optional_int(row.get("wafer_y")),
                "die_x": _optional_int(row.get("die_x")),
                "die_y": _optional_int(row.get("die_y")),
                "rough_bin": _optional_int(row.get("rough_bin")),
                "class_number": _optional_int(row.get("class_number")),
                "test_id": _optional_int(row.get("test_id")),
                "label": _optional_str(row.get("label")),
                "predicted_label": _optional_str(row.get("predicted_label")),
                "confidence": _optional_float(row.get("confidence")),
            }
            for column in columns:
                out[column] = image_bytes.get((row_index, column))
            materialized_rows.append(out)
        return _rows_to_table(materialized_rows, schema=schema)

    def _append_error(
        self,
        errors: list[dict[str, str]],
        error: dict[str, str],
    ) -> None:
        if len(errors) < self._max_error_records:
            errors.append(error)


def _next_batch(batches: Iterator[pl.DataFrame]) -> pl.DataFrame | None:
    return next(batches, None)


def _unlink_if_exists(path: str) -> None:
    if os.path.isfile(path):
        os.unlink(path)


def _normalize_inspection_time(raw: object) -> str:
    dt = parse_inspection_time(raw)
    if dt is None:
        return ""
    return dt.isoformat()


def _materialized_column_name(image_type: str) -> str:
    normalized = image_type.strip().lower()
    match normalized:
        # image-parser normalizes patch aliases before returning streamed
        # results, so a patch_template request comes back as "Reference".
        case (
            "reference"
            | "patch_reference"
            | "patchreference"
            | "template"
            | "patch_template"
            | "patchtemplate"
        ):
            return "patch_template_bytes"
        case "defective" | "patch_defective" | "patchdefective":
            return "patch_defective_bytes"
        case "difference" | "patch_difference" | "patchdifference":
            return "patch_difference_bytes"
        case _:
            safe = "".join(c if c.isalnum() else "_" for c in normalized).strip("_")
            return f"{safe}_bytes" if safe else "image_bytes"


def _image_role(image_type: str) -> str:
    normalized = image_type.strip().lower()
    match normalized:
        case "template" | "patch_template" | "patchtemplate":
            return "patch_template"
        case "defective" | "patch_defective" | "patchdefective":
            return "patch_defective"
        case "difference" | "patch_difference" | "patchdifference":
            return "patch_difference"
        case _:
            return normalized


def _rows_to_table(
    rows: list[dict[str, Any]],
    *,
    schema: pa.Schema,
) -> pa.Table:
    return pa.Table.from_pylist(rows, schema=schema)


def _optional_str(raw: object) -> str | None:
    if raw is None:
        return None
    return str(raw)


def _optional_int(raw: object) -> int | None:
    if raw is None:
        return None
    if not isinstance(raw, str | int | float | bool):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _optional_float(raw: object) -> float | None:
    if raw is None:
        return None
    if not isinstance(raw, str | int | float | bool):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None
