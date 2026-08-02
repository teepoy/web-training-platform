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
from app.modules.sc.domain.models import parse_inspection_time
from app.modules.sc.schema import find_images_by_role
from app.modules.sc.app.services.training_images import (
    normalize_sc_training_row,
    readable_image_bytes,
)
from app.modules.types import catalog

SC_PATCH_IMAGE_MATERIALIZER = catalog.get_materializer_meta(
    "sc-inspection-patch-image-v1"
)


class ScMaterializationCapacityError(RuntimeError):
    """The configured materialized-output budget was exceeded."""


class ScInspectionMaterializer:
    def __init__(
        self,
        image_source: Any,
        *,
        schema_registry: DataPlaneSchemaRegistry,
        batch_rows: int,
        max_error_records: int,
        temp_dir: str | None = None,
    ) -> None:
        if batch_rows <= 0:
            raise ValueError("batch_rows must be greater than zero")
        if max_error_records <= 0:
            raise ValueError("max_error_records must be greater than zero")
        self._image_source = image_source
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
        requested_roles = {
            _materialized_column_name(image_type): _image_role(image_type)
            for image_type in image_types
        }
        errors: list[dict[str, str]] = []
        columns = [_materialized_column_name(t) for t in image_types]
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
                        requested_roles=requested_roles,
                        image_types=image_types,
                        columns=columns,
                        errors=errors,
                    )
                    logical_output_bytes += table.nbytes
                    if logical_output_bytes > max_output_bytes:
                        raise ScMaterializationCapacityError(
                            "SC materialization exceeded configured output budget: "
                            f"{logical_output_bytes} > {max_output_bytes} bytes"
                        )
                    if writer is None:
                        writer = pq.ParquetWriter(handle.name, table.schema)
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
                await asyncio.to_thread(pq.write_table, _rows_to_table([]), handle.name)
            size_bytes = os.path.getsize(handle.name)
            if size_bytes > max_output_bytes:
                raise ScMaterializationCapacityError(
                    "SC materialization Parquet exceeded configured output budget: "
                    f"{size_bytes} > {max_output_bytes} bytes"
                )
            schema = self._schema_registry.get(
                SC_PATCH_IMAGE_MATERIALIZER.output_view.contract,
                SC_PATCH_IMAGE_MATERIALIZER.output_view.schema_version,
            )
            manifest = DataPlaneManifest.from_schema(
                view_contract=SC_PATCH_IMAGE_MATERIALIZER.output_view.contract,
                view_schema_version=(
                    SC_PATCH_IMAGE_MATERIALIZER.output_view.schema_version
                ),
                dataset_id=dataset_id,
                job_id=job_id,
                format="parquet",
                schema=schema,
                schema_ref=self._schema_registry.schema_ref(
                    SC_PATCH_IMAGE_MATERIALIZER.output_view.contract,
                    SC_PATCH_IMAGE_MATERIALIZER.output_view.schema_version,
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
        requested_roles: dict[str, str],
        image_types: list[str],
        columns: list[str],
        errors: list[dict[str, str]],
    ) -> pa.Table:
        image_bytes: dict[tuple[str, int, str, str], bytes] = {}
        missing_by_inspection: dict[tuple[str, int], set[int]] = {}
        for row in rows:
            inspection_time = str(row.get("inspection_time") or "")
            wafer_key = int(row.get("wafer_key", 0) or 0)
            defect_id = str(row.get("defect_id") or "")
            images = row.get("images")
            if not isinstance(images, list):
                images = []
            missing_role = False
            for column, role in requested_roles.items():
                refs = find_images_by_role(images, role)
                raw = refs[0].get("bytes") if refs else None
                readable = readable_image_bytes(raw)
                if readable is None:
                    missing_role = True
                    continue
                image_bytes[(inspection_time, wafer_key, defect_id, column)] = readable
            if not missing_role:
                continue
            try:
                numeric_defect_id = int(defect_id)
            except ValueError:
                self._append_error(
                    errors,
                    {
                        "defect_id": defect_id,
                        "image_type": ",".join(requested_roles),
                        "error": (
                            "missing local bytes and defect_id is not "
                            "upstream-resolvable"
                        ),
                    },
                )
                continue
            missing_by_inspection.setdefault((inspection_time, wafer_key), set()).add(
                numeric_defect_id
            )

        for (inspection_time, wafer_key), defect_ids in missing_by_inspection.items():
            async for item in self._image_source.stream_inspection_images(
                inspection_time=inspection_time,
                wafer_key=wafer_key,
                defect_ids=sorted(defect_ids),
                image_types=image_types,
            ):
                defect_id = str(item.get("defect_id", ""))
                image_type = _materialized_column_name(str(item.get("image_type", "")))
                error = str(item.get("error", "") or "")
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
                image_bytes[(inspection_time, wafer_key, defect_id, image_type)] = (
                    bytes(item.get("image_data", b""))
                )

        materialized_rows: list[dict[str, Any]] = []
        for row in rows:
            defect_id = str(row.get("defect_id", ""))
            inspection_time = str(row.get("inspection_time") or "")
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
                out[column] = image_bytes.get(
                    (inspection_time, wafer_key, defect_id, column)
                )
            materialized_rows.append(out)
        return _rows_to_table(materialized_rows)

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


def _rows_to_table(rows: list[dict[str, Any]]) -> pa.Table:
    arrays = {
        "sample_id": pa.array(_str_values(rows, "sample_id"), type=pa.string()),
        "inspection_time": pa.array(
            _str_values(rows, "inspection_time"),
            type=pa.string(),
        ),
        "wafer_key": pa.array(_int_values(rows, "wafer_key"), type=pa.int64()),
        "defect_id": pa.array(_str_values(rows, "defect_id"), type=pa.string()),
        "wafer_x": pa.array(_int_values(rows, "wafer_x"), type=pa.int64()),
        "wafer_y": pa.array(_int_values(rows, "wafer_y"), type=pa.int64()),
        "die_x": pa.array(_int_values(rows, "die_x"), type=pa.int64()),
        "die_y": pa.array(_int_values(rows, "die_y"), type=pa.int64()),
        "rough_bin": pa.array(_int_values(rows, "rough_bin"), type=pa.int64()),
        "class_number": pa.array(
            _int_values(rows, "class_number"),
            type=pa.int64(),
        ),
        "test_id": pa.array(_int_values(rows, "test_id"), type=pa.int64()),
        "label": pa.array(_nullable_str_values(rows, "label"), type=pa.string()),
        "predicted_label": pa.array(
            _nullable_str_values(rows, "predicted_label"),
            type=pa.string(),
        ),
        "confidence": pa.array(
            _float_values(rows, "confidence"),
            type=pa.float64(),
        ),
        "patch_template_bytes": pa.array(
            _binary_values(rows, "patch_template_bytes"),
            type=pa.binary(),
        ),
        "patch_defective_bytes": pa.array(
            _binary_values(rows, "patch_defective_bytes"),
            type=pa.binary(),
        ),
    }
    return pa.table(arrays)


def _str_values(rows: list[dict[str, Any]], key: str) -> list[str]:
    return [_optional_str(row.get(key)) or "" for row in rows]


def _nullable_str_values(rows: list[dict[str, Any]], key: str) -> list[str | None]:
    return [_optional_str(row.get(key)) for row in rows]


def _int_values(rows: list[dict[str, Any]], key: str) -> list[int | None]:
    return [_optional_int(row.get(key)) for row in rows]


def _float_values(rows: list[dict[str, Any]], key: str) -> list[float | None]:
    return [_optional_float(row.get(key)) for row in rows]


def _binary_values(rows: list[dict[str, Any]], key: str) -> list[bytes | None]:
    return [_optional_bytes(row.get(key)) for row in rows]


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


def _optional_bytes(raw: object) -> bytes | None:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        return raw
    if isinstance(raw, bytearray):
        return bytes(raw)
    return None
