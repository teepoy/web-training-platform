from __future__ import annotations

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


class LinkLabelStudioRequest(BaseModel):
    ls_project_id: str


class SyncPredictionsResponse(BaseModel):
    synced_count: int = 0
    skipped_count: int = 0
    errors: list[str] = Field(default_factory=list)


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


class LatestPrediction(BaseModel):
    id: str
    predicted_label: str
    score: float
    model_artifact_id: str


class SampleWithLabels(BaseModel):
    id: str
    dataset_id: str
    image_uris: list[str]
    metadata: dict
    ls_task_id: int | None = None
    latest_annotation: LatestAnnotation | None = None
    latest_prediction: LatestPrediction | None = None


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
