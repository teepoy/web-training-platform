from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from app.core.registry import dataset


@dataset
class ClassificationSample(BaseModel):
    ID: ClassVar[str] = "image_classification"
    VIEW_TYPES: ClassVar[set[str]] = {"image_input_v1", "labeled_image_v1"}
    TASK_TYPE: ClassVar[str] = "classification"

    sample_id: str
    image_uris: list[str]
    metadata: dict = {}
    label: str = ""
