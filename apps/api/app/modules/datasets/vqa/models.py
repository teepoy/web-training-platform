from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from app.core.registry import dataset


@dataset
class VQASample(BaseModel):
    ID: ClassVar[str] = "image_vqa"
    VIEW_TYPES: ClassVar[set[str]] = {"image_input_v1", "qa_input_v1"}
    TASK_TYPE: ClassVar[str] = "vqa"

    sample_id: str
    image_uris: list[str]
    question: str = ""
    answer: str = ""
    metadata: dict = {}
