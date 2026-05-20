from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from croniter import croniter
from pydantic import BaseModel, Field, field_validator

from app.domain.models import ModelSpec, TaskSpec
from app.domain.types import DatasetType

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int


class CreateDatasetRequest(BaseModel):
    name: str
    dataset_type: DatasetType | None = None
    task_spec: TaskSpec = Field(default_factory=TaskSpec)


class CreateSampleRequest(BaseModel):
    image_uris: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class BulkCreateSampleItem(BaseModel):
    image_uris: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    label: str | None = None


class BulkCreateSampleRequest(BaseModel):
    items: list[BulkCreateSampleItem] = Field(default_factory=list)


class CreatePresetRequest(BaseModel):
    name: str
    model_spec: ModelSpec
    omegaconf_yaml: str
    dataloader_ref: str


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


class WaferPoint(BaseModel):
    id: str
    x: float
    y: float


class WaferPointsResponse(BaseModel):
    points: list[WaferPoint]
    total: int


class HealthStatus(BaseModel):
    status: str
    auth_enabled: bool


class UploadResponse(BaseModel):
    uri: str
    sample_id: str
    index: int


class SyncResult(BaseModel):
    synced_count: int
    skipped_count: int = 0
    errors: list[str] = Field(default_factory=list)


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


class BatchPredictionResponse(BaseModel):
    model_id: str
    dataset_id: str
    total_samples: int
    successful: int
    failed: int
    predictions: list[Any]
    started_at: datetime
    completed_at: datetime
    model_version: str | None = None


class MetadataKeyInfo(BaseModel):
    type: str = Field(description="Polars-inferred type name, e.g. 'Utf8', 'Int64'")
    null_count: int = 0
    n_unique: int = 0
    sample_values: list = Field(
        default_factory=list, description="Up to 5 example values"
    )
    min: float | int | None = None
    max: float | int | None = None


class DeclaredMetadataKey(BaseModel):
    type: str = Field(description="Expected type, e.g. 'string', 'integer', 'float'")
    description: str = Field(
        default="", description="Human-readable description of this key"
    )


class DataSourceApi(BaseModel):
    kind: str = Field(default="api", pattern="^api$")
    endpoint: str
    params: dict[str, str] = Field(default_factory=dict)
    refresh_interval: int = Field(
        default=0, ge=0, description="Auto-refresh in ms; 0 = off"
    )


class DataSourceContext(BaseModel):
    kind: str = Field(default="context", pattern="^context$")
    key: str
    path: str | None = None


class AgentPanelDescriptor(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9\-]*$", max_length=80)
    component: str = Field(description="Key into the frontend plugin registry")
    title: str = Field(max_length=120)
    order: int = Field(default=50, ge=0)
    collapsed: bool = False
    size: str = Field(default="normal", pattern="^(compact|normal|large)$")
    data: dict | None = Field(
        default=None, description="Inline data payload: {inline: <payload>}"
    )
    data_source: DataSourceApi | DataSourceContext | None = Field(
        default=None, description="Reference to a data source"
    )
    config: dict = Field(
        default_factory=dict, description="Widget-specific config props"
    )
    ephemeral: bool = Field(
        default=False, description="Auto-remove on next agent turn if not re-sent"
    )
    ttl: int | None = Field(
        default=None, ge=1, description="Auto-remove after N seconds"
    )


class SurfaceLayout(BaseModel):
    width: int = Field(default=280, ge=100, le=800)
    position: str = Field(default="right", pattern="^(right|left)$")


class SurfaceStateDocument(BaseModel):
    version: int = Field(default=1)
    surface_id: str
    panels: list[AgentPanelDescriptor] = Field(default_factory=list)
    layout: SurfaceLayout = Field(default_factory=SurfaceLayout)
    exported_at: str | None = None
    metadata: dict = Field(
        default_factory=dict, description="Optional provenance: created_by, description"
    )


class SetPanelRequest(BaseModel):
    panel: AgentPanelDescriptor


class AgentEventMessage(BaseModel):
    type: str = Field(default="message")
    content: str


class AgentEventAction(BaseModel):
    type: str = Field(default="action")
    tool: str
    summary: str
    result: dict | None = None


class WidgetManifest(BaseModel):
    key: str
    description: str
    config_schema: dict = Field(
        default_factory=dict, description="JSON Schema for config props"
    )
    data_schema: dict = Field(
        default_factory=dict, description="JSON Schema for inline data"
    )


class QueryDataRequest(BaseModel):
    query_type: str = Field(
        description="One of: annotation-stats, sample-slice, metadata-histogram, recent-annotations, prediction-summary, wafer-points"
    )
    params: dict = Field(default_factory=dict)


class AgentContext(BaseModel):
    page: str = Field(
        default="", description="Current route path, e.g. '/datasets/abc/classify'"
    )
    dataset_id: str | None = Field(
        default=None, description="Active dataset ID if on a dataset page"
    )
    job_id: str | None = Field(
        default=None, description="Active job ID if on a job page"
    )
    schedule_id: str | None = Field(
        default=None, description="Active schedule ID if on a schedule page"
    )
    extra: dict = Field(
        default_factory=dict, description="Arbitrary extra context from the frontend"
    )


class GlobalChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    context: AgentContext = Field(default_factory=AgentContext)
    session_id: str | None = Field(
        default=None, description="Resume existing session; omit for auto-generated"
    )


class PredictionCollectionRequest(BaseModel):
    name: str
    dataset_id: str
    model_id: str
    prediction_ids: list[str] = Field(default_factory=list)
    model_version: str | None = None
    target: str = "image_classification"
    source_job_id: str | None = None


class TaskTrackerCheckResult(BaseModel):
    key: str
    label: str
    status: str
    message: str = ""
    value: str | None = None


class TaskTrackerScorecard(BaseModel):
    errors: int = 0
    warnings: int = 0
    checks: list[TaskTrackerCheckResult] = Field(default_factory=list)


class TaskTrackerNode(BaseModel):
    key: str
    label: str
    status: str
    detail: str = ""
    expected_start_at: datetime | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class TaskTrackerStage(BaseModel):
    key: str
    label: str
    status: str
    summary: str = ""
    nodes: list[TaskTrackerNode] = Field(default_factory=list)


class TaskTrackerSummaryMetrics(BaseModel):
    total: int | None = None
    processed: int | None = None
    successful: int | None = None
    failed: int | None = None
    skipped: int | None = None
    rate_hint: str | None = None


class TaskTrackerDeepLinks(BaseModel):
    prefect_run_url: str | None = None
    prefect_deployment_url: str | None = None
    platform_job_url: str | None = None


class TaskTrackerRawPayload(BaseModel):
    platform_job: dict = Field(default_factory=dict)
    flow_run: dict | None = None
    deployment: dict | None = None
    work_queue: dict | None = None
    work_pool: dict | None = None
    logs: list[dict] = Field(default_factory=list)


class TaskTrackerDerived(BaseModel):
    task_kind: str
    execution_kind: str
    display_status: str
    prefect_state: str | None = None
    stage: str
    active_node: str | None = None
    capacity_status: str = "unknown"
    queue_priority: int | None = None
    queue_priority_label: str = "none"
    queue_depth_ahead: int | None = None
    pool_concurrency_limit: int | None = None
    pool_slots_used: int | None = None
    stages: list[TaskTrackerStage] = Field(default_factory=list)
    scorecard: TaskTrackerScorecard = Field(default_factory=TaskTrackerScorecard)
    summary_metrics: TaskTrackerSummaryMetrics = Field(
        default_factory=TaskTrackerSummaryMetrics
    )
    artifacts: list[dict] = Field(default_factory=list)
    dynamic_console_lines: list[str] = Field(default_factory=list)
    deep_links: TaskTrackerDeepLinks = Field(default_factory=TaskTrackerDeepLinks)


class TaskTrackerSummaryResponse(BaseModel):
    id: str
    task_kind: str
    execution_kind: str
    display_name: str
    display_status: str
    stage: str
    dataset_id: str
    model_id: str | None = None
    preset_id: str | None = None
    created_by: str
    created_at: datetime
    updated_at: datetime
    prefect_state: str | None = None
    work_pool_name: str | None = None
    work_queue_name: str | None = None
    queue_priority: int | None = None
    queue_priority_label: str = "none"
    queue_depth_ahead: int | None = None
    capacity_status: str = "unknown"
    pool_concurrency_limit: int | None = None
    pool_slots_used: int | None = None


class TaskTrackerDetailResponse(BaseModel):
    id: str
    task_kind: str
    meta: dict = Field(default_factory=dict)
    raw: TaskTrackerRawPayload
    derived: TaskTrackerDerived
