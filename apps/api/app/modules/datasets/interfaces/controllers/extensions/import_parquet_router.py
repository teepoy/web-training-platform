from __future__ import annotations

# pyright: reportMissingImports=false

import io
import logging
from typing import TypeGuard

import pyarrow.parquet as pq
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pyarrow import Table as ArrowTable

from app.shared.api.schemas import Annotation, Organization, Sample, User, SPARSE_NO_LS
from app.shared.api.schemas import TaskType
from app.modules.auth.interfaces.controllers.deps import (
    get_current_org,
    get_current_user,
)
from app.modules.datasets.interfaces.dtos.schemas import (
    BulkCreateSampleItem,
    BulkCreateSampleResponse,
)
from app.modules.datasets.api.deps import LabelStudioClientDep
from app.shared.db.sql_repository import SqlRepository
from app.modules.datasets.application.sample_access.factory import SampleAccessFactory
from app.shared.deps import (  # pyright: ignore[reportMissingImports]
    get_repository,
    get_sample_access_factory,
)
from app.shared.infrastructure.label_studio.client import (
    platform_annotation_to_ls,
)

router = APIRouter(prefix="/api/v1/plugins/import-parquet", tags=["plugins"])
_logger = logging.getLogger(__name__)


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
        c for c in table.column_names if c not in image_cols and c != label_col
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


@router.post("/import", response_model=BulkCreateSampleResponse)
async def import_parquet(
    dataset_id: str,
    ls_client: LabelStudioClientDep,
    repo: SqlRepository = Depends(get_repository),
    sample_factory: SampleAccessFactory = Depends(get_sample_access_factory),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> BulkCreateSampleResponse:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    access = sample_factory.create(dataset.storage_mode)
    if not dataset.ls_project_id or dataset.ls_project_id == SPARSE_NO_LS:
        raise HTTPException(
            status_code=500,
            detail="Dataset has no Label Studio project — cannot create sample.",
        )

    content = await file.read()
    try:
        table = pq.read_table(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid parquet file: {exc}")

    if table.num_rows == 0:
        raise HTTPException(status_code=400, detail="Parquet file has no rows")

    items, warnings = _parquet_to_sample_items(table)
    if not items:
        raise HTTPException(
            status_code=400, detail="No importable rows found in parquet file"
        )

    for w in warnings:
        _logger.warning("parquet import [%s]: %s", dataset_id, w)

    ls_tasks: list[dict] = []
    for item in items:
        from urllib.parse import quote

        image_url = (
            f"/api/v1/images/resolve?uri={quote(item.image_uris[0], safe='')}"
            if item.image_uris
            else ""
        )
        task_data: dict = {"image": image_url}
        if dataset.task_spec.task_type == TaskType.VQA:
            task_data["question"] = str(item.metadata.get("question", ""))
        ls_tasks.append(task_data)

    try:
        imported = await ls_client.import_tasks(
            int(dataset.ls_project_id),
            ls_tasks,
            return_task_ids=True,
        )
        task_ids = [int(tid) for tid in imported.get("task_ids", [])]  # type: ignore[arg-type]
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

    samples = [
        Sample(
            dataset_id=dataset_id,
            image_uris=item.image_uris,
            metadata=item.metadata,
            ls_task_id=task_ids[idx],
        )
        for idx, item in enumerate(items)
    ]
    created = await access.create_samples(samples)

    for idx, item in enumerate(items):
        if item.label is None:
            continue
        sample = created[idx]
        if sample.ls_task_id is not None:
            await ls_client.create_annotation(
                sample.ls_task_id,
                platform_annotation_to_ls(item.label),
            )
        await repo.create_annotation(
            Annotation(
                sample_id=sample.id,
                label=item.label,
                created_by=current_user.email,
            ),
            user_id=current_user.id,
        )

    return BulkCreateSampleResponse(
        dataset_id=dataset_id,
        imported=len(created),
        failed=0,
        sample_ids=[s.id for s in created],
        ls_task_ids=task_ids,
        errors=warnings,
    )
