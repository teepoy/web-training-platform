from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.domain.types import DatasetType, JobStatus, ModelFramework, OrgRole, TaskType


DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"


class ArtifactRef(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    uri: str
    kind: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Model-specific fields (optional)
    name: str | None = None
    file_size: int | None = None
    file_hash: str | None = None
    format: str | None = None
    created_at: datetime | None = None


class Model(ArtifactRef):
    """A trained model artifact with additional context."""
    job_id: str
    dataset_id: str | None = None
    dataset_name: str | None = None
    preset_id: str | None = None
    preset_name: str | None = None


class TaskSpec(BaseModel):
    task_type: TaskType = TaskType.CLASSIFICATION
    label_space: list[str] = Field(default_factory=list)


class Dataset(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    dataset_type: DatasetType = DatasetType.IMAGE_CLASSIFICATION
    task_spec: TaskSpec = Field(default_factory=TaskSpec)
    org_id: str | None = DEFAULT_ORG_ID
    org_name: str = ""
    is_public: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    embed_config: dict = Field(default_factory=dict)
    ls_project_id: str | None = None
    ls_project_url: str | None = None


class Sample(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    dataset_id: str
    image_uris: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    ls_task_id: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Annotation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    sample_id: str
    label: str
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ModelSpec(BaseModel):
    framework: ModelFramework = ModelFramework.PYTORCH
    base_model: str


class TrainingPreset(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    model_spec: ModelSpec
    omegaconf_yaml: str
    dataloader_ref: str
    org_id: str | None = DEFAULT_ORG_ID


class TrainingEvent(BaseModel):
    job_id: str
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    level: str = "info"
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)


class TrainingJob(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    dataset_id: str
    preset_id: str
    status: JobStatus = JobStatus.QUEUED
    created_by: str
    org_id: str | None = DEFAULT_ORG_ID
    org_name: str = ""
    is_public: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    artifact_refs: list[ArtifactRef] = Field(default_factory=list)


class SampleFeature(BaseModel):
    sample_id: str
    embedding: list[float] = Field(default_factory=list)
    embed_model: str | None = None
    computed_at: datetime | None = None


class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    email: str
    name: str
    is_superadmin: bool = False
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Organization(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    slug: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrgMembership(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    org_id: str
    role: OrgRole
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PredictionReviewAction(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    dataset_id: str
    model_id: str
    model_version: str | None = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AnnotationVersion(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    review_action_id: str
    annotation_id: str
    source_prediction_id: int | None = None
    predicted_label: str
    final_label: str
    confidence: float | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PredictionEvent(BaseModel):
    job_id: str
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    level: str = "info"
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)


class PredictionJob(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    dataset_id: str
    model_id: str
    status: JobStatus = JobStatus.QUEUED
    created_by: str
    target: str = "image_classification"
    model_version: str | None = None
    org_id: str | None = DEFAULT_ORG_ID
    org_name: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    external_job_id: str | None = None
    sample_ids: list[str] | None = None
    summary: dict[str, Any] = Field(default_factory=dict)


class UserWithOrgs(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    email: str
    name: str
    is_superadmin: bool = False
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    organizations: list[OrgMembership] = Field(default_factory=list)
