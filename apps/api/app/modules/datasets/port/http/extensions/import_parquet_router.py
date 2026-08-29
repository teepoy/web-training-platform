from __future__ import annotations

# pyright: reportMissingImports=false

import json
import logging
from collections.abc import AsyncIterator
from typing import TypeGuard
from uuid import uuid4

import pyarrow.parquet as pq
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pyarrow import Table as ArrowTable

from app.core.config import AppConfig
from app.shared.api.schemas import (
    Annotation,
    DatasetStorageMode,
    Organization,
    SPARSE_NO_LS,
    User,
)
from app.modules.auth.port.http.deps import (
    get_current_org,
    get_current_user,
)
from app.modules.datasets.port.http.schemas import (
    BulkCreateSampleItem,
    BulkCreateSampleResponse,
)
from app.modules.datasets.port.http.deps import LabelStudioClientDep
from app.modules.datasets.domain.repository import DatasetRepository
from app.modules.datasets.port.http.deps import (
    get_config,
    get_repository,
    get_dataset_storage_factory,
)
from app.modules.storage.adapter.factory import DatasetStorageFactory
from app.modules.datasets.domain.sample_row import BulkSampleRow
from app.shared.infrastructure.label_studio.client import (
    platform_annotation_to_ls,
)

router = APIRouter(prefix="/api/v1/plugins/import-parquet", tags=["plugins"])
_logger = logging.getLogger(__name__)
_PORTABLE_SAMPLE_ID_KEY = "__platform_sample_id"


def _is_image_struct(value: object) -> TypeGuard[dict[str, object]]:
    """Check if a value looks like a HuggingFace image struct {bytes, path}."""
    if not isinstance(value, dict):
        return False
    return "bytes" in value or "path" in value


def _extract_image_uri(col_name: str, value: object) -> list[str]:
    """Extract image URI(s) from a parquet cell.

    HuggingFace image columns are structs with ``bytes`` (binary) and
    ``path`` (string) fields.  For import we store the ``path`` as the
    sample's ``image_uri`` — the actual byte content is too large for
    inline storage and the caller typically has the images on a shared
    volume or object store.
    """
    if value is None:
        return []
    if _is_image_struct(value):
        path = value.get("path")
        if path and isinstance(path, str):
            return [path]
        return []
    if isinstance(value, list):
        uris: list[str] = []
        for v in value:
            if _is_image_struct(v):
                path = v.get("path")
                if path and isinstance(path, str):
                    uris.append(path)
        return uris
    return []


def _find_image_columns(table: ArrowTable) -> list[str]:
    """Heuristic: columns whose first non-null value is an image struct."""
    image_cols: list[str] = []
    for col_name in table.column_names:
        col = table.column(col_name)
        for val in col:
            if val.is_valid:
                scalar = val.as_py()
                if _is_image_struct(scalar) or (
                    isinstance(scalar, list)
                    and len(scalar) > 0
                    and _is_image_struct(scalar[0])
                ):
                    image_cols.append(col_name)
                    break
    return image_cols


def _find_label_column(table: ArrowTable, image_cols: list[str]) -> str | None:
    """Heuristic: first string column named *label* or *class* (not an image col)."""
    for col_name in table.column_names:
        if col_name in image_cols:
            continue
        lower = col_name.lower()
        if lower in ("label", "class", "category", "labels"):
            return col_name
    return None


def _parquet_to_sample_items(
    table: ArrowTable,
) -> tuple[list[BulkCreateSampleItem], list[str]]:
    """Convert an Arrow table to BulkCreateSampleItem list.

    Returns (items, warnings).
    """
    image_cols = _find_image_columns(table)
    label_col = _find_label_column(table, image_cols)
    metadata_cols = [
        c
        for c in table.column_names
        if c not in image_cols and c not in {label_col, "sample_id", "metadata"}
    ]

    warnings: list[str] = []
    if not image_cols:
        warnings.append(
            "No image columns detected (expected struct with 'bytes'/'path'). "
            "Samples will have empty image_uris."
        )

    items: list[BulkCreateSampleItem] = []
    for row_idx in range(table.num_rows):
        image_uris: list[str] = []
        for ic in image_cols:
            val = table.column(ic)[row_idx].as_py()
            image_uris.extend(_extract_image_uri(ic, val))

        label: str | None = None
        if label_col:
            raw = table.column(label_col)[row_idx].as_py()
            if raw is not None:
                label = str(raw)

        metadata: dict[str, object] = {}
        if "metadata" in table.column_names:
            raw_metadata = table.column("metadata")[row_idx].as_py()
            if isinstance(raw_metadata, dict):
                metadata.update(raw_metadata)
            elif isinstance(raw_metadata, str):
                try:
                    decoded_metadata = json.loads(raw_metadata)
                except json.JSONDecodeError:
                    metadata["metadata"] = raw_metadata
                else:
                    if isinstance(decoded_metadata, dict):
                        metadata.update(decoded_metadata)
                    else:
                        metadata["metadata"] = raw_metadata
            elif raw_metadata is not None:
                metadata["metadata"] = raw_metadata
        if "sample_id" in table.column_names:
            raw_sample_id = table.column("sample_id")[row_idx].as_py()
            if raw_sample_id is not None:
                metadata[_PORTABLE_SAMPLE_ID_KEY] = str(raw_sample_id)
        for mc in metadata_cols:
            val = table.column(mc)[row_idx].as_py()
            if val is not None:
                metadata[mc] = val

        items.append(
            BulkCreateSampleItem(
                image_uris=image_uris,
                metadata=metadata,
                label=label,
            )
        )

    return items, warnings


async def _collect_bulk_rows_parquet(
    rows: list[BulkSampleRow],
) -> AsyncIterator[BulkSampleRow]:
    for row in rows:
        yield row


@router.post("/import", response_model=BulkCreateSampleResponse)
async def import_parquet(
    dataset_id: str,
    ls_client: LabelStudioClientDep,
    repo: DatasetRepository = Depends(get_repository),
    factory: DatasetStorageFactory = Depends(get_dataset_storage_factory),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    config: AppConfig = Depends(get_config),
) -> BulkCreateSampleResponse:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    if dataset.storage_mode != DatasetStorageMode.DB_FULL:
        raise HTTPException(
            status_code=422,
            detail="Parquet import currently requires db_full Dataset storage",
        )
    if not dataset.ls_project_id or dataset.ls_project_id == SPARSE_NO_LS:
        raise HTTPException(
            status_code=500,
            detail="Dataset has no Label Studio project — cannot create sample.",
        )
    storage = await factory.open(dataset_id, org_id=org.id)

    await file.seek(0)
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    if file_size > config.dataset_transfer.parquet_import_max_bytes:
        raise HTTPException(
            status_code=413,
            detail="Parquet import exceeds the configured byte limit",
        )
    try:
        parquet_file = pq.ParquetFile(file.file)
        if (
            parquet_file.metadata.num_rows
            > config.dataset_transfer.parquet_import_max_rows
        ):
            raise HTTPException(
                status_code=413,
                detail="Parquet import exceeds the configured row limit",
            )
        table = parquet_file.read()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid parquet file: {exc}")

    if table.num_rows == 0:
        raise HTTPException(status_code=400, detail="Parquet file has no rows")

    items, warnings = _parquet_to_sample_items(table)
    if not items:
        raise HTTPException(
            status_code=400, detail="No importable rows found in parquet file"
        )

    allowed_labels = set(dataset.task_spec.label_space)
    unknown_labels = sorted(
        {
            item.label
            for item in items
            if item.label is not None and item.label not in allowed_labels
        }
    )
    if unknown_labels:
        raise HTTPException(
            status_code=422,
            detail=(
                "Parquet labels are not in the target Dataset label space: "
                + ", ".join(unknown_labels[:5])
            ),
        )

    for w in warnings:
        _logger.warning("parquet import [%s]: %s", dataset_id, w)

    sample_ids = [
        str(item.metadata.pop(_PORTABLE_SAMPLE_ID_KEY, "")).strip() or uuid4().hex
        for item in items
    ]
    if len(sample_ids) != len(set(sample_ids)):
        raise HTTPException(
            status_code=422, detail="Parquet sample_id values must be unique"
        )
    existing_sample_ids = await repo.existing_sample_ids(set(sample_ids))
    if existing_sample_ids:
        raise HTTPException(
            status_code=409,
            detail=(
                "Parquet sample_id values already exist in the target Dataset: "
                + ", ".join(sorted(existing_sample_ids)[:5])
            ),
        )

    ls_tasks: list[dict] = []
    for item in items:
        from urllib.parse import quote

        image_url = (
            f"/api/v1/images/resolve?uri={quote(item.image_uris[0], safe='')}"
            if item.image_uris
            else ""
        )
        task_data: dict = {"image": image_url}
        ls_tasks.append(task_data)

    try:
        imported = await ls_client.import_tasks(
            int(dataset.ls_project_id),
            ls_tasks,
            return_task_ids=True,
        )
        imported_dict: dict = imported if isinstance(imported, dict) else {}
        task_ids = [int(tid) for tid in imported_dict.get("task_ids", [])]
        if len(task_ids) != len(items):
            raise HTTPException(
                status_code=502,
                detail="Label Studio bulk import returned mismatched task IDs.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Label Studio bulk import failed: {exc}"
        )

    bulk_rows = [
        BulkSampleRow(
            sample_id=sample_ids[idx],
            image_uris=list(item.image_uris),
            metadata=dict(item.metadata),
            label=item.label,
            extra={"ls_task_id": task_ids[idx]},
        )
        for idx, item in enumerate(items)
    ]

    await storage.write_samples(_collect_bulk_rows_parquet(bulk_rows))

    ann_list: list[Annotation] = []
    for idx, item in enumerate(items):
        if item.label is None:
            continue
        sid = sample_ids[idx]
        ls_tid = task_ids[idx]
        await ls_client.create_annotation(
            ls_tid,
            platform_annotation_to_ls(item.label),
        )
        ann_list.append(
            Annotation(
                sample_id=sid,
                label=item.label,
                created_by=current_user.email,
            )
        )
    if ann_list:
        await storage.create_annotations(ann_list)

    return BulkCreateSampleResponse(
        dataset_id=dataset_id,
        imported=len(sample_ids),
        failed=0,
        sample_ids=sample_ids,
        ls_task_ids=task_ids,
        errors=warnings,
    )
