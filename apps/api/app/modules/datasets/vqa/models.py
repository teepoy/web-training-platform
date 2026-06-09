from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from app.core.registry import dataset, view


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


class VQADataset(BaseModel):
    dataset_id: str
    name: str
    task_type: str = "vqa"
    label_space: list[str] = []
    storage_mode: str = "db_full"
    ls_project_id: str = ""
    samples: list[VQASample] = []
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
class QAInputV1(BaseModel):
    view_id: ClassVar[str] = "qa_input_v1"
    view_name: ClassVar[str] = "QA Input"
    is_annotation_view: ClassVar[bool] = True

    sample_id: str
    image_uris: list[str]
    question: str
