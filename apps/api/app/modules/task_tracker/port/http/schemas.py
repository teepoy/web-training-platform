from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


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
    dataset_id: str
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
