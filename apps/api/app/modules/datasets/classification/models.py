from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from app.core.registry import dataset, view


@dataset
class ClassificationSample(BaseModel):
    ID: ClassVar[str] = "image_classification"
    VIEW_TYPES: ClassVar[set[str]] = {"image_input_v1", "labeled_image_v1"}
    TASK_TYPE: ClassVar[str] = "classification"

    sample_id: str
    image_uris: list[str]
    metadata: dict = {}
    label: str = ""


class ClassificationDataset(BaseModel):
    dataset_id: str
    name: str
    task_type: str = "classification"
    label_space: list[str] = []
    storage_mode: str = "db_full"
    ls_project_id: str = ""
    samples: list[ClassificationSample] = []
    metadata: dict = {}


# ── View types ──────────────────────────────────────────────────────


@view
class ImageInputV1(BaseModel):
    view_id: ClassVar[str] = "image_input_v1"
    view_name: ClassVar[str] = "Image Input"
    is_annotation_view: ClassVar[bool] = False

    sample_id: str
    image_uris: list[str]


@view
class LabeledImageV1(BaseModel):
    view_id: ClassVar[str] = "labeled_image_v1"
    view_name: ClassVar[str] = "Labeled Image"
    is_annotation_view: ClassVar[bool] = True

    sample_id: str
    image_uris: list[str]
    label: str
