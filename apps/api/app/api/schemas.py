from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from croniter import croniter
from pydantic import BaseModel, Field, field_validator

from app.domain.models import ModelSpec, TaskSpec

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int


class CreateDatasetRequest(BaseModel):
    name: str
    task_spec: TaskSpec = Field(default_factory=TaskSpec)


class UpdateLabelSpaceRequest(BaseModel):
    label_space: list[str]


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


class UpdateEmbedConfigRequest(BaseModel):
    model: str
    dimension: int = 512


class UpdateSampleImageResponse(BaseModel):
    uri: str
    sample_id: str
    index: int


class CreateScheduleRequest(BaseModel):
    name: str
    flow_name: str
    cron: str
    parameters: dict = Field(default_factory=dict)
    description: str = ""

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        if not croniter.is_valid(v):
            raise ValueError("invalid cron expression")
        return v


class UpdateScheduleRequest(BaseModel):
    name: str | None = None
    cron: str | None = None
    parameters: dict | None = None
    description: str | None = None
    is_schedule_active: bool | None = None

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, v: str | None) -> str | None:
        if v is not None and not croniter.is_valid(v):
            raise ValueError("invalid cron expression")
        return v


class ScheduleResponse(BaseModel):
    id: str
    name: str
    flow_name: str
    cron: str | None = None
    parameters: dict = Field(default_factory=dict)
    description: str = ""
    is_schedule_active: bool = True
    created: str | None = None
    updated: str | None = None
    prefect_deployment_id: str


class RunResponse(BaseModel):
    id: str
    name: str
    deployment_id: str | None = None
    flow_name: str | None = None
    state_type: str | None = None
    state_name: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    total_run_time: float | None = None
    parameters: dict = Field(default_factory=dict)


class RunLogResponse(BaseModel):
    id: str | None = None
    flow_run_id: str | None = None
    level: int
    timestamp: str
    message: str


class BulkAnnotationItem(BaseModel):
    sample_id: str
    label: str
    annotator: str = "platform-user"


class BulkAnnotationRequest(BaseModel):
    annotations: list[BulkAnnotationItem]


class LatestAnnotation(BaseModel):
    id: str
    label: str
    created_by: str
    created_at: str


class SampleWithLabels(BaseModel):
    id: str
    dataset_id: str
    image_uris: list[str]
    metadata: dict
    ls_task_id: int | None = None
    latest_annotation: LatestAnnotation | None = None


# ---------------------------------------------------------------------------
# Dashboard schemas
# ---------------------------------------------------------------------------


class WorkPoolStatus(BaseModel):
    name: str
    type: str
    is_paused: bool
    concurrency_limit: int | None = None
    slots_used: int = 0
    status: str = "unknown"


class JobQueueStats(BaseModel):
    queued: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0


class RecentJobSummary(BaseModel):
    id: str
    dataset_id: str
    preset_id: str
    status: str
    created_by: str
    created_at: str
    updated_at: str


class DashboardResponse(BaseModel):
    work_pool: WorkPoolStatus | None = None
    job_queue: JobQueueStats = Field(default_factory=JobQueueStats)
    recent_jobs: list[RecentJobSummary] = Field(default_factory=list)
    prefect_connected: bool = False


# ---------------------------------------------------------------------------
# Auth / User schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    is_superadmin: bool
    created_at: datetime


class MembershipResponse(BaseModel):
    org_id: str
    org_name: str
    org_slug: str
    role: str


class UserWithOrgsResponse(BaseModel):
    id: str
    email: str
    name: str
    is_superadmin: bool
    created_at: datetime
    organizations: list[MembershipResponse] = Field(default_factory=list)


class LoginResponse(BaseModel):
    access_token: str
    user: UserResponse


# ---------------------------------------------------------------------------
# Org management schemas
# ---------------------------------------------------------------------------


class CreateOrgRequest(BaseModel):
    name: str
    slug: str = ""


class OrgResponse(BaseModel):
    id: str
    name: str
    slug: str
    created_at: datetime


class AddMemberRequest(BaseModel):
    user_id: str
    role: str = "member"


class MemberResponse(BaseModel):
    id: str
    user_id: str
    user_email: str
    user_name: str
    role: str
    created_at: datetime


# ---------------------------------------------------------------------------
# PAT schemas
# ---------------------------------------------------------------------------


class CreateTokenRequest(BaseModel):
    name: str


class TokenResponse(BaseModel):
    id: str
    name: str
    token_prefix: str
    created_at: datetime


class TokenCreatedResponse(BaseModel):
    id: str
    name: str
    token: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Model asset schemas
# ---------------------------------------------------------------------------


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


class SetPublicRequest(BaseModel):
    is_public: bool


# ---------------------------------------------------------------------------
# Model management schemas
# ---------------------------------------------------------------------------


class ModelResponse(BaseModel):
    """Response schema for model artifacts."""
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
    """Request metadata for model upload (file sent separately)."""
    name: str
    format: str = Field(description="Model format: pytorch, onnx, safetensors, keras")
    job_id: str = Field(description="Training job ID to associate the model with")


# ---------------------------------------------------------------------------
# Prediction schemas
# ---------------------------------------------------------------------------


class RunPredictionRequest(BaseModel):
    """Request to run predictions on a dataset using a model."""
    model_id: str = Field(description="ID of the model artifact to use")
    dataset_id: str = Field(description="ID of the dataset to run predictions on")
    sample_ids: list[str] | None = Field(
        default=None,
        description="Optional list of sample IDs. If None, runs on all samples in dataset",
    )
    model_version: str | None = Field(
        default=None,
        description="Optional version tag for Label Studio filtering",
    )


class PredictionResultResponse(BaseModel):
    """Result of a single sample prediction."""
    sample_id: str
    ls_task_id: int | None = None
    predicted_label: str
    confidence: float | None = None
    ls_prediction_id: int | None = None
    error: str | None = None


class BatchPredictionResponse(BaseModel):
    """Response for batch prediction run."""
    model_id: str
    dataset_id: str
    total_samples: int
    successful: int
    failed: int
    predictions: list[PredictionResultResponse]
    started_at: datetime
    completed_at: datetime
    model_version: str | None = None


class PredictSingleRequest(BaseModel):
    """Request to predict a single sample."""
    model_id: str = Field(description="ID of the model artifact to use")
    sample_id: str = Field(description="ID of the sample to predict")
    model_version: str | None = Field(
        default=None,
        description="Optional version tag for Label Studio filtering",
    )
