from __future__ import annotations

import os
import tempfile
from contextlib import ExitStack
from collections.abc import Iterable, Iterator
from typing import Any

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
_PARQUET_WRITE_BATCH_SIZE = 256


class _ParquetRowDataset:
    """Re-iterable row view over materialized Parquet without a second cache."""

    def __init__(self, path: str, row_count: int) -> None:
        self._path = path
        self._row_count = row_count

    def __len__(self) -> int:
        return self._row_count

    def __iter__(self) -> Iterator[dict[str, Any]]:
        parquet_file = pq.ParquetFile(self._path)
        for batch in parquet_file.iter_batches(batch_size=_PARQUET_WRITE_BATCH_SIZE):
            yield from batch.to_pylist()


class ScInspectionMaterializer:
    def __init__(
        self,
        image_source: Any,
        *,
        schema_registry: DataPlaneSchemaRegistry,
        temp_dir: str | None = None,
    ) -> None:
        self._image_source = image_source
        self._schema_registry = schema_registry
        self._temp_dir = temp_dir

    async def materialize(
        self,
        *,
        rows_lazyframe: Any,
        dataset_id: str = "",
        job_id: str = "",
        image_types: list[str] | None = None,
    ) -> ScInspectionMaterialization:
        image_types = image_types or list(DEFAULT_PATCH_IMAGE_TYPES)
        df = rows_lazyframe.collect()
        if df.height == 0:
            return await self._write_rows(
                (),
                [],
                row_count=0,
                dataset_id=dataset_id,
                job_id=job_id,
                image_types=image_types,
            )

        requested_roles = {
            _materialized_column_name(image_type): _image_role(image_type)
            for image_type in image_types
        }
        image_bytes: dict[tuple[str, int, str, str], bytes] = {}
        errors: list[dict[str, str]] = []

        missing_by_inspection: dict[tuple[str, int], set[int]] = {}
        for raw_row in df.iter_rows(named=True):
            row = normalize_sc_training_row(dict(raw_row))
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
                if readable is not None:
                    image_bytes[(inspection_time, wafer_key, defect_id, column)] = (
                        readable
                    )
                else:
                    missing_role = True
            if missing_role:
                try:
                    numeric_defect_id = int(defect_id)
                except ValueError:
                    errors.append(
                        {
                            "defect_id": defect_id,
                            "image_type": ",".join(requested_roles),
                            "error": "missing local bytes and defect_id is not upstream-resolvable",
                        }
                    )
                    continue
                missing_by_inspection.setdefault(
                    (inspection_time, wafer_key), set()
                ).add(numeric_defect_id)

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
                    errors.append(
                        {
                            "defect_id": defect_id,
                            "image_type": image_type,
                            "error": error,
                        }
                    )
                    continue
                image_bytes[(inspection_time, wafer_key, defect_id, image_type)] = (
                    bytes(item.get("image_data", b""))
                )

        columns = [_materialized_column_name(t) for t in image_types]

        def materialized_rows() -> Iterator[dict[str, Any]]:
            for raw_row in df.iter_rows(named=True):
                row = normalize_sc_training_row(dict(raw_row))
                defect_id = str(row.get("defect_id", ""))
                inspection_time = str(row.get("inspection_time") or "")
                wafer_key = int(row.get("wafer_key", 0) or 0)
                out = {
                    "sample_id": str(row.get("sample_id", "")),
                    "defect_id": defect_id,
                    "inspection_time": _normalize_inspection_time(
                        row.get("inspection_time")
                    ),
                    "wafer_key": int(row.get("wafer_key", 0) or 0),
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
                yield out

        return await self._write_rows(
            materialized_rows(),
            errors,
            row_count=df.height,
            dataset_id=dataset_id,
            job_id=job_id,
            image_types=image_types,
        )

    async def _write_rows(
        self,
        rows: Iterable[dict[str, Any]],
        errors: list[dict[str, str]],
        *,
        row_count: int,
        dataset_id: str,
        job_id: str,
        image_types: list[str],
    ) -> ScInspectionMaterialization:
        with ExitStack() as cleanup:
            handle = tempfile.NamedTemporaryFile(
                suffix=".parquet", delete=False, dir=self._temp_dir
            )
            handle.close()
            cleanup.callback(_unlink_if_exists, handle.name)
            written_rows = _write_parquet_batches(rows, handle.name)
            if written_rows != row_count:
                raise RuntimeError(
                    f"materializer row count changed while writing: "
                    f"expected {row_count}, wrote {written_rows}"
                )
            size_bytes = os.path.getsize(handle.name)
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
                cache_dir=None,
                dataset=_ParquetRowDataset(handle.name, row_count),
                row_count=row_count,
                manifest=manifest,
                errors=errors,
            )
            cleanup.pop_all()
            return materialization


def _write_parquet_batches(
    rows: Iterable[dict[str, Any]],
    path: str,
) -> int:
    writer: pq.ParquetWriter | None = None
    batch: list[dict[str, Any]] = []
    written_rows = 0
    try:
        for row in rows:
            batch.append(row)
            if len(batch) < _PARQUET_WRITE_BATCH_SIZE:
                continue
            table = _rows_to_table(batch)
            writer = writer or pq.ParquetWriter(path, table.schema)
            writer.write_table(table)
            written_rows += len(batch)
            batch.clear()
        if batch:
            table = _rows_to_table(batch)
            writer = writer or pq.ParquetWriter(path, table.schema)
            writer.write_table(table)
            written_rows += len(batch)
        if writer is None:
            pq.write_table(_rows_to_table([]), path)
        return written_rows
    finally:
        if writer is not None:
            writer.close()


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
        case "template" | "patch_template" | "patchtemplate":
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
