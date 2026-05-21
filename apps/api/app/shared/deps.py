from __future__ import annotations

from typing import Any

from fastapi import Depends

from app.domain.models import Dataset
from app.domain.types import DatasetType, TaskType


def get_container() -> Any:
    from app.main import container

    return container


def get_repository(c: Any = Depends(get_container)) -> Any:
    return c.repository()


def get_artifact_storage(c: Any = Depends(get_container)) -> Any:
    return c.artifact_storage()


def get_label_studio_client(c: Any = Depends(get_container)) -> Any:
    return c.label_studio_client()


def get_sample_access_factory(c: Any = Depends(get_container)) -> Any:
    return c.sample_access_factory()


def get_task_tracker(c: Any = Depends(get_container)) -> Any:
    return c.task_tracker()


def get_model_service(c: Any = Depends(get_container)) -> Any:
    return c.model_service()


def get_sensor_repository(c: Any = Depends(get_container)) -> Any:
    return c.sensor_repository()


def get_sensor_dispatch(c: Any = Depends(get_container)) -> Any:
    return c.sensor_dispatch()


def get_sensor_dispatch_service(c: Any = Depends(get_container)) -> Any:
    return c.sensor_dispatch()


def get_sensor_registry(c: Any = Depends(get_container)) -> Any:
    return c.sensor_registry()


def _infer_dataset_type(task_type: TaskType) -> DatasetType:
    if task_type == TaskType.VQA:
        return DatasetType.IMAGE_VQA
    return DatasetType.IMAGE_CLASSIFICATION


def _make_ls_image_url(uri: str) -> str:
    """Convert platform image URI to LS-accessible URL."""
    from urllib.parse import quote

    if uri.startswith(("s3://", "memory://")):
        return f"/api/v1/images/resolve?uri={quote(uri, safe='')}"
    return uri


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
