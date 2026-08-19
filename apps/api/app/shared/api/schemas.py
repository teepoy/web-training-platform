from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Generic, TypeVar
from uuid import uuid4

from croniter import croniter
from pydantic import BaseModel, Field, field_validator

T = TypeVar("T")


class DatasetStorageMode(str, Enum):
    DB_FULL = "db_full"
    FILE_SHARD_SPARSE = "file_shard_sparse"


class ModelFramework(str, Enum):
    PYTORCH = "pytorch"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OrgRole(str, Enum):
    ADMIN = "admin"
    MEMBER = "member"


SPARSE_NO_LS = "SPARSE_NO_LS"


class ArtifactRef(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    uri: str
    kind: str
    metadata: dict[str, object] = Field(default_factory=dict)
    name: str | None = None
    file_size: int | None = None
    file_hash: str | None = None
    format: str | None = None
    created_at: datetime | None = None


class Model(ArtifactRef):
    job_id: str
    dataset_id: str | None = None
    dataset_name: str | None = None
    collection_id: str | None = None
    collection_revision_id: str | None = None
    collection_name: str | None = None
    trainer_id: str | None = None
    trainer_name: str | None = None
    created_by: str = "system"
    creator_name: str = ""


class TaskSpec(BaseModel):
    task_type: str = "classification"
    label_space: list[str] = Field(default_factory=list)
    metadata_schema: dict[str, dict[str, str]] = Field(default_factory=dict)


class ImageSourceBinding(BaseModel):
    """Filesystem image contract and code-registered format selected by a Dataset.

    Filesystem roots, network credentials, staging policy, ownership, and cache
    policy belong to the runtime entrypoint, never Dataset metadata. ``format``
    remains nullable so historical bindings are readable without backfilling;
    operations that need images reject a missing format explicitly.
    """

    contract: str = Field(min_length=1)
    format: str | None = Field(default=None, min_length=1)


class Dataset(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    dataset_type: str = "image_classification"
    task_spec: TaskSpec = Field(default_factory=TaskSpec)
    view_types: list[str] = Field(default_factory=list)
    org_id: str | None = None
    org_name: str = ""
    created_by: str = "system"
    creator_name: str = ""
    is_public: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    embed_config: dict = Field(default_factory=dict)
    ls_project_id: str | None = None
    ls_project_url: str | None = None
    storage_mode: DatasetStorageMode = DatasetStorageMode.DB_FULL
    dataset_meta: dict = Field(default_factory=dict)
    image_source: ImageSourceBinding | None = None


class CreatorSummary(BaseModel):
    id: str
    name: str


class Sample(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    dataset_id: str
    image_uris: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    ls_task_id: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Annotation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    sample_id: str
    label: str
    annotation_value: dict | list | None = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TrainingEvent(BaseModel):
    job_id: str
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    level: str = "info"
    message: str
    payload: dict[str, object] = Field(default_factory=dict)


class TrainingJob(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    # Historical jobs outlive their source dataset.  The database FK uses
    # ON DELETE SET NULL, so read models must preserve that state instead of
    # failing every job-list query after a dataset is removed.
    dataset_id: str | None
    dataset_revision_id: str | None = Field(
        default=None,
        description=(
            "Dataset Revision observed when the job was submitted; audit-only and "
            "does not select the runtime input"
        ),
    )
    collection_id: str | None = None
    collection_revision_id: str | None = None
    trainer_id: str
    status: JobStatus = JobStatus.QUEUED
    created_by: str
    org_id: str | None = None
    org_name: str = ""
    is_public: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    external_job_id: str | None = None
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
    oauth_provider: str | None = None
    oauth_provider_id: str | None = None


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
    collection_id: str | None = None
    sync_tag: str | None = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PlatformPrediction(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    org_id: str
    dataset_id: str
    sample_id: str
    model_id: str
    target: str = "image_classification"
    job_id: str | None = None
    model_version: str | None = None
    predicted_label: str
    confidence: float | None = None
    all_scores: dict[str, float] | None = None
    error: str | None = None
    created_by: str = "system"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PredictionCollection(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    org_id: str
    dataset_id: str
    model_id: str
    name: str
    model_version: str | None = None
    target: str = "image_classification"
    source_job_id: str | None = None
    sync_tag: str | None = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PredictionCollectionItem(BaseModel):
    collection_id: str
    prediction_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AnnotationVersion(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    review_action_id: str
    annotation_id: str
    prediction_id: str | None = None
    predicted_label: str
    final_label: str
    confidence: float | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PredictionEvent(BaseModel):
    job_id: str
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    level: str = "info"
    message: str
    payload: dict[str, object] = Field(default_factory=dict)


class PredictionJob(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    # See TrainingJob.dataset_id: prediction history is retained after the
    # source dataset is deleted.
    dataset_id: str | None
    dataset_revision_id: str | None = Field(
        default=None,
        description=(
            "Dataset Revision observed when the job was submitted; audit-only and "
            "does not select the runtime input"
        ),
    )
    collection_id: str | None = None
    collection_revision_id: str | None = None
    model_id: str
    status: JobStatus = JobStatus.QUEUED
    created_by: str
    target: str = "image_classification"
    model_version: str | None = None
    org_id: str | None = None
    org_name: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    external_job_id: str | None = None
    sample_ids: list[str] | None = None
    summary: dict[str, object] = Field(default_factory=dict)


class UserWithOrgs(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    email: str
    name: str
    is_superadmin: bool = False
    orgs: list[Organization] = Field(default_factory=list)


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int


class CreateDatasetRequest(BaseModel):
    name: str
    dataset_type: str | None = None
    task_spec: TaskSpec = Field(default_factory=TaskSpec)
    storage_mode: DatasetStorageMode = DatasetStorageMode.DB_FULL


class UpdateLabelSpaceRequest(BaseModel):
    label_space: list[str]


class CreateSampleRequest(BaseModel):
    image_uris: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class BulkCreateSampleItem(BaseModel):
    image_uris: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    label: str | None = None


class BulkCreateSampleRequest(BaseModel):
    items: list[BulkCreateSampleItem] = Field(default_factory=list)


class BulkCreateSampleResponse(BaseModel):
    dataset_id: str
    imported: int
    failed: int
    sample_ids: list[str] = Field(default_factory=list)
    ls_task_ids: list[int] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class CreateAnnotationRequest(BaseModel):
    dataset_id: str
    sample_id: str
    label: str
    annotation_value: dict | list | None = None
    created_by: str = "demo-user"


class UpdateAnnotationRequest(BaseModel):
    dataset_id: str
    label: str


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


class BulkAnnotationResponse(BaseModel):
    created: int


class SyncAnnotationsResponse(BaseModel):
    synced_count: int
    errors: list[str] = Field(default_factory=list)


class CancelJobResponse(BaseModel):
    cancelled: bool


class MarkLeftResponse(BaseModel):
    marked: bool


class SetPublicResponse(BaseModel):
    ok: bool


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


class WaferPoint(BaseModel):
    id: str
    x: float
    y: float


class WaferPointsResponse(BaseModel):
    points: list[WaferPoint]
    total: int


class SampleEmbedResponse(BaseModel):
    sample_id: str
    embed_model: str
    embedding_dim: int


class PersistExportResponse(BaseModel):
    uri: str


class VersionExportPersistResponse(BaseModel):
    uri: str
    format_id: str


class SimilarityNeighbor(BaseModel):
    sample_id: str
    score: float


class SimilarityResponse(BaseModel):
    sample_id: str
    neighbors: list[SimilarityNeighbor] = Field(default_factory=list)


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
    dataset_id: str | None
    trainer_id: str
    status: str
    created_by: str
    created_at: str
    updated_at: str


class ServiceStatus(BaseModel):
    name: str
    kind: str
    status: str
    detail: str = ""
    latency_ms: int | None = None
    endpoint: str | None = None


class DatasetAnnotationStats(BaseModel):
    total_samples: int = 0
    annotated_samples: int = 0
    unlabeled_samples: int = 0
    label_counts: dict[str, int] = Field(default_factory=dict)


class DashboardResponse(BaseModel):
    work_pool: WorkPoolStatus | None = None
    job_queue: JobQueueStats = Field(default_factory=JobQueueStats)
    recent_jobs: list[RecentJobSummary] = Field(default_factory=list)
    services: list[ServiceStatus] = Field(default_factory=list)
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
    trainer_name: str


class UploadModelRequest(BaseModel):
    """Request metadata for model upload (file sent separately)."""

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
    gpu_job_id: str | None = None
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
    dataset_id: str | None
    dataset_name: str | None = None
    model_id: str | None = None
    trainer_id: str | None = None
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


# ---------------------------------------------------------------------------
# Agent / Display Surface schemas
# ---------------------------------------------------------------------------


class MetadataKeyInfo(BaseModel):
    """Describes a single metadata key discovered by scanning sample data."""

    type: str = Field(description="Polars-inferred type name, e.g. 'Utf8', 'Int64'")
    null_count: int = 0
    n_unique: int = 0
    sample_values: list = Field(
        default_factory=list, description="Up to 5 example values"
    )
    min: float | int | None = None
    max: float | int | None = None


class DeclaredMetadataKey(BaseModel):
    """Human-declared metadata key description (stored in task_spec.metadata_schema)."""

    type: str = Field(description="Expected type, e.g. 'string', 'integer', 'float'")
    description: str = Field(
        default="", description="Human-readable description of this key"
    )


class DataSourceApi(BaseModel):
    """Data source that fetches from a backend API endpoint."""

    kind: str = Field(default="api", pattern="^api$")
    endpoint: str
    params: dict[str, str] = Field(default_factory=dict)
    refresh_interval: int = Field(
        default=0, ge=0, description="Auto-refresh in ms; 0 = off"
    )


class DataSourceContext(BaseModel):
    """Data source that reads from an injected Vue provide/inject context."""

    kind: str = Field(default="context", pattern="^context$")
    key: str
    path: str | None = None


class AgentPanelDescriptor(BaseModel):
    """Describes a single panel that the agent wants to render on a display surface."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9\-]*$", max_length=80)
    component: str = Field(description="Key into the frontend widget registry")
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
    """Layout settings for a display surface."""

    width: int = Field(default=280, ge=100, le=800)
    position: str = Field(default="right", pattern="^(right|left)$")


class SurfaceStateDocument(BaseModel):
    """Complete serialisable state of a display surface."""

    version: int = Field(default=1)
    surface_id: str
    panels: list[AgentPanelDescriptor] = Field(default_factory=list)
    layout: SurfaceLayout = Field(default_factory=SurfaceLayout)
    exported_at: str | None = None
    metadata: dict = Field(
        default_factory=dict, description="Optional provenance: created_by, description"
    )


class SetPanelRequest(BaseModel):
    """Request body for adding / replacing a panel on a surface."""

    panel: AgentPanelDescriptor


class ChatRequest(BaseModel):
    """User message sent to the agent."""

    message: str = Field(min_length=1, max_length=4000)


class AgentEventMessage(BaseModel):
    """Agent text response event."""

    type: str = Field(default="message")
    content: str


class AgentEventAction(BaseModel):
    """Agent tool-call action event."""

    type: str = Field(default="action")
    tool: str
    summary: str
    result: dict | None = None


class WidgetManifest(BaseModel):
    """Describes a widget type available on a surface."""

    key: str
    description: str
    config_schema: dict = Field(
        default_factory=dict, description="JSON Schema for config props"
    )
    data_schema: dict = Field(
        default_factory=dict, description="JSON Schema for inline data"
    )


class QueryDataRequest(BaseModel):
    """Structured data query from the agent."""

    query_type: str = Field(
        description="One of: annotation-stats, sample-slice, metadata-histogram, recent-annotations, prediction-summary, wafer-points"
    )
    params: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Global Agent schemas
# ---------------------------------------------------------------------------


class AgentContext(BaseModel):
    """Client-provided context for the global agent.

    Tells the agent what page the user is on and what entity they are
    looking at, so the system prompt can be enriched accordingly.
    """

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
    """User message sent to the global agent."""

    message: str = Field(min_length=1, max_length=4000)
    context: AgentContext = Field(default_factory=AgentContext)
    session_id: str | None = Field(
        default=None, description="Resume existing session; omit for auto-generated"
    )


# --- Preview session schemas ---


class CreatePreviewSessionRequest(BaseModel):
    collection_ref: str


class PreviewItemResponse(BaseModel):
    upstream_item_id: str
    image_uris: list[str]
    metadata: dict[str, Any] = {}


class PreviewSessionResponse(BaseModel):
    session_id: str
    collection_ref: str
    classification_enabled: (
        bool  # always False in preview (read-only flag for frontend)
    )
    estimated_total: int | None
    loaded_count: int
    next_cursor: str | None
    has_more: bool


class PreviewItemsResponse(BaseModel):
    items: list[PreviewItemResponse]
    next_cursor: str | None
    has_more: bool
    estimated_total: int | None


class StartPersistRequest(BaseModel):
    scope: str = "entire_collection"


class PersistStatusResponse(BaseModel):
    dataset_id: str
    persist_session_id: str
    status: str
    imported_count: int
    remaining_count: int
    error: str | None


# ---------------------------------------------------------------------------
# Sparse summary
# ---------------------------------------------------------------------------


class SparseShardSummary(BaseModel):
    shard_index: int
    row_count: int
    format: str
    byte_size: int


class SparseManifestSummary(BaseModel):
    shard_count: int
    total_rows: int
    schema_columns: list[dict[str, str]]
    created_at: str


class SparseSummaryResponse(BaseModel):
    dataset_id: str
    name: str
    dataset_type: str
    storage_mode: str
    manifest: SparseManifestSummary
    shards: list[SparseShardSummary]
    sample_rows: list[dict[str, object]]
