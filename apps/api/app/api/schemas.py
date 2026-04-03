from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from app.domain.models import ModelSpec, TaskSpec

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int


class CreateDatasetRequest(BaseModel):
    name: str
    task_spec: TaskSpec = Field(default_factory=TaskSpec)


class CreateSampleRequest(BaseModel):
    image_uris: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class CreateAnnotationRequest(BaseModel):
    sample_id: str
    label: str
    created_by: str = "demo-user"


class UpdateAnnotationRequest(BaseModel):
    label: str


class CreatePresetRequest(BaseModel):
    name: str
    model_spec: ModelSpec
    omegaconf_yaml: str
    dataloader_ref: str


class CreateTrainingJobRequest(BaseModel):
    dataset_id: str
    preset_id: str
    created_by: str = "demo-user"


class CreatePredictionRequest(BaseModel):
    sample_id: str
    predicted_label: str
    score: float
    model_artifact_id: str


class EditPredictionRequest(BaseModel):
    corrected_label: str
    edited_by: str = "demo-user"


class UpdateEmbedConfigRequest(BaseModel):
    model: str
    dimension: int = 512


class UpdateSampleImageResponse(BaseModel):
    uri: str
    sample_id: str
    index: int
