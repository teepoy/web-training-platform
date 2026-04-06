from __future__ import annotations

from pydantic import BaseModel

from app.domain.types import DatasetType, ModelFramework, TaskType


class DatasetContract(BaseModel):
    id: str
    name: str
    dataset_type: DatasetType


class TaskContract(BaseModel):
    task_type: TaskType
    label_space: list[str]


class ModelContract(BaseModel):
    framework: ModelFramework
    base_model: str
