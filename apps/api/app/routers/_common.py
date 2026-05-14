from __future__ import annotations

from app.domain.models import Dataset
from app.domain.types import DatasetType, TaskType


def get_container():
    """Lazy container accessor — import happens at call time, not module load."""
    from app.main import container

    return container


def _infer_dataset_type(task_type: TaskType) -> DatasetType:
    if task_type == TaskType.VQA:
        return DatasetType.IMAGE_VQA
    return DatasetType.IMAGE_CLASSIFICATION


def _make_ls_image_url(uri: str) -> str:
    """Convert platform image URI to LS-accessible URL."""
    from urllib.parse import quote

    if uri.startswith(("s3://", "memory://")):
        return f"/api/v1/images/resolve?uri={quote(uri, safe='')}"
    return uri  # data: URIs and http:// pass through


def _with_ls_url(dataset: Dataset) -> Dataset:
    """Compute ls_project_url at response time from config.

    Uses external_url (browser-facing) if available, falls back to url (internal).
    Sparse datasets use a sentinel ``ls_project_id`` — no LS URL is returned.
    """
    from app.domain.models import SPARSE_NO_LS

    if dataset.ls_project_id == SPARSE_NO_LS:
        return dataset
    cfg = get_container().config()
    # Prefer external_url for browser access, fall back to internal url
    ls_url = str(cfg.label_studio.external_url or cfg.label_studio.url).rstrip("/")
    if dataset.ls_project_id and ls_url:
        return dataset.model_copy(
            update={"ls_project_url": f"{ls_url}/projects/{dataset.ls_project_id}"}
        )
    return dataset
