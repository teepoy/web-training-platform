from __future__ import annotations

from urllib.parse import quote

from app.shared.api.schemas import DatasetType, TaskType


def infer_dataset_type(task_type: TaskType) -> DatasetType:
    if task_type == TaskType.VQA:
        return DatasetType.IMAGE_VQA
    return DatasetType.IMAGE_CLASSIFICATION


def make_ls_image_url(uri: str) -> str:
    """Convert platform image URI to LS-accessible URL."""
    if uri.startswith(("s3://", "memory://")):
        return f"/api/v1/images/resolve?uri={quote(uri, safe='')}"
    return uri


_infer_dataset_type = infer_dataset_type
_make_ls_image_url = make_ls_image_url
