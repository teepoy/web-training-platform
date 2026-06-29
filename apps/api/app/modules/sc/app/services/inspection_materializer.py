from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from importlib import import_module
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from app.modules.sc.domain.models import parse_inspection_time


DEFAULT_PATCH_IMAGE_TYPES = ["patch_template", "patch_defective"]


@dataclass
class ScInspectionMaterialization:
    parquet_path: str
    dataset: Any
    row_count: int
    errors: list[dict[str, str]] = field(default_factory=list)

    def cleanup(self) -> None:
        if os.path.isfile(self.parquet_path):
            os.unlink(self.parquet_path)


class ScInspectionMaterializer:
    def __init__(self, image_fetcher: Any, *, temp_dir: str | None = None) -> None:
        self._image_fetcher = image_fetcher
        self._temp_dir = temp_dir

    async def materialize(
        self,
        *,
        rows_lazyframe: Any,
        image_types: list[str] | None = None,
    ) -> ScInspectionMaterialization:
        image_types = image_types or list(DEFAULT_PATCH_IMAGE_TYPES)
        df = rows_lazyframe.collect()
        rows = list(df.iter_rows(named=True))
        if not rows:
            return await self._write_rows([], [])

        inspection_time = str(rows[0].get("inspection_time", ""))
        wafer_key = int(rows[0].get("wafer_key", 0) or 0)
        defect_ids = sorted(
            {
                int(row.get("defect_id"))
                for row in rows
                if row.get("defect_id") is not None
            }
        )
        image_bytes: dict[tuple[str, str], bytes] = {}
        errors: list[dict[str, str]] = []

        async for item in self._image_fetcher.stream_inspection_images(
            inspection_time=inspection_time,
            wafer_key=wafer_key,
            defect_ids=defect_ids,
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
            image_bytes[(defect_id, image_type)] = bytes(item.get("image_data", b""))

        materialized_rows: list[dict[str, Any]] = []
        columns = [_materialized_column_name(t) for t in image_types]
        for row in rows:
            defect_id = str(row.get("defect_id", ""))
            out = {
                "sample_id": str(row.get("sample_id", "")),
                "defect_id": defect_id,
                "inspection_time": _normalize_inspection_time(
                    row.get("inspection_time")
                ),
                "wafer_key": int(row.get("wafer_key", 0) or 0),
            }
            for column in columns:
                out[column] = image_bytes.get((defect_id, column))
            materialized_rows.append(out)

        return await self._write_rows(materialized_rows, errors)

    async def _write_rows(
        self, rows: list[dict[str, Any]], errors: list[dict[str, str]]
    ) -> ScInspectionMaterialization:
        handle = tempfile.NamedTemporaryFile(
            suffix=".parquet", delete=False, dir=self._temp_dir
        )
        handle.close()
        table = _rows_to_table(rows)
        pq.write_table(table, handle.name)

        datasets_module = import_module("datasets")
        ds = datasets_module.load_dataset(
            "parquet", data_files=handle.name, split="train"
        )
        return ScInspectionMaterialization(
            parquet_path=handle.name,
            dataset=ds,
            row_count=len(rows),
            errors=errors,
        )


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


def _rows_to_table(rows: list[dict[str, Any]]) -> pa.Table:
    if not rows:
        return pa.table(
            {
                "sample_id": pa.array([], type=pa.string()),
                "defect_id": pa.array([], type=pa.string()),
                "inspection_time": pa.array([], type=pa.string()),
                "wafer_key": pa.array([], type=pa.int64()),
                "patch_template_bytes": pa.array([], type=pa.binary()),
                "patch_defective_bytes": pa.array([], type=pa.binary()),
            }
        )
    keys = sorted({key for row in rows for key in row})
    arrays = {}
    for key in keys:
        values = [row.get(key) for row in rows]
        if key.endswith("_bytes"):
            arrays[key] = pa.array(values, type=pa.binary())
        elif key == "wafer_key":
            arrays[key] = pa.array(values, type=pa.int64())
        else:
            arrays[key] = pa.array(values, type=pa.string())
    return pa.table(arrays)
