from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from app.core.registry import dataset, view


class BoxV1(BaseModel):
    label: str
    x: float
    y: float
    width: float
    height: float


@dataset
class DetectionSample(BaseModel):
    ID: ClassVar[str] = "image_detection"
    VIEW_TYPES: ClassVar[set[str]] = {"image_input_v1", "box_detection_v1"}
    TASK_TYPE: ClassVar[str] = "detection"

    sample_id: str
    image_uris: list[str]
    metadata: dict = {}
    boxes: list[BoxV1] = []
    width: int | None = None
    height: int | None = None


class DetectionDataset(BaseModel):
    dataset_id: str
    name: str
    task_type: str = "detection"
    label_space: list[str] = []
    storage_mode: str = "db_full"
    ls_project_id: str = ""
    samples: list[DetectionSample] = []
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
class BoxDetectionV1(BaseModel):
    view_id: ClassVar[str] = "box_detection_v1"
    view_name: ClassVar[str] = "Box Detection"
    is_annotation_view: ClassVar[bool] = True

    sample_id: str
    image_uris: list[str]
    boxes: list[BoxV1]
    width: int | None = None
    height: int | None = None
