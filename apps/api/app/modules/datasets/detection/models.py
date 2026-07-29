from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from app.core.registry import dataset


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
