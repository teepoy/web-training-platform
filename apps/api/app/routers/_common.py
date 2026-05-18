from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.container import Container

from app.domain.models import Dataset
from app.domain.types import DatasetType, TaskType


def get_container() -> Container:
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
    """Compute ls_project_url and capabilities at response time."""
    from app.domain.models import SPARSE_NO_LS

    c = get_container()
    access = c.sample_access_factory().create(dataset.storage_mode)
    dataset = dataset.model_copy(update={"capabilities": access.capabilities()})

    if dataset.ls_project_id == SPARSE_NO_LS:
        return dataset
    cfg = c.config()
    ls_url = str(cfg.label_studio.external_url or cfg.label_studio.url).rstrip("/")
    if dataset.ls_project_id and ls_url:
        return dataset.model_copy(
            update={"ls_project_url": f"{ls_url}/projects/{dataset.ls_project_id}"}
        )
    return dataset
