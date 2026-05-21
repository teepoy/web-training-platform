from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SetPublicResponse(BaseModel):
    ok: bool


class SetPublicRequest(BaseModel):
    is_public: bool


class ModelAssetVersion(BaseModel):
    id: str
    uri: str
    kind: str
    metadata: dict = Field(default_factory=dict)
    is_public: bool = False
    org_name: str = ""


class ModelAssetSummary(BaseModel):
    dataset_id: str
    total: int = 0
    assets: list[ModelAssetVersion] = Field(default_factory=list)
    is_public: bool = False
    org_name: str = ""


class ModelResponse(BaseModel):
    id: str
    uri: str
    kind: str
    name: str | None = None
    file_size: int | None = None
    file_hash: str | None = None
    format: str | None = None
    created_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)
    job_id: str
    dataset_id: str
    dataset_name: str
    preset_name: str


class UploadModelRequest(BaseModel):
    name: str
    format: str = Field(description="Model format: pytorch, onnx, safetensors, keras")
    job_id: str = Field(description="Training job ID to associate the model with")


class ModelCompatibilityRequest(BaseModel):
    dataset_types: list[str] = Field(default_factory=list)
    task_types: list[str] = Field(default_factory=list)
    prediction_targets: list[str] = Field(default_factory=list)
    label_space: list[str] = Field(default_factory=list)
    embedding_dimension: int | None = None
    normalized_output: bool | None = None


class UploadModelSpecRequest(BaseModel):
    framework: str
    architecture: str
    base_model: str


class UploadModelMetadataRequest(BaseModel):
    name: str
    format: str = Field(description="Model format: pytorch, onnx, safetensors, keras")
    job_id: str = Field(description="Training job ID to associate the model with")
    template_id: str
    profile_id: str = "custom"
    model_spec: UploadModelSpecRequest
    compatibility: ModelCompatibilityRequest


class UploadTemplateProfileResponse(BaseModel):
    id: str
    name: str
    model_spec: dict = Field(default_factory=dict)
    default_prediction_targets: list[str] = Field(default_factory=list)


class ModelUploadTemplateResponse(BaseModel):
    id: str
    name: str
    dataset_types: list[str] = Field(default_factory=list)
    task_types: list[str] = Field(default_factory=list)
    profiles: list[UploadTemplateProfileResponse] = Field(default_factory=list)
    label_space_mode: str = "forbidden"
    requires_embedding_metadata: bool = False
