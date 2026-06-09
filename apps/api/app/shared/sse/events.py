from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, RootModel

from app.shared.api.schemas import TaskTrackerDetailResponse


class AgentMessageEvent(BaseModel):
    event_type: Literal["agent-message"]
    content: str


class AgentActionEvent(BaseModel):
    event_type: Literal["agent-action"]
    tool: str
    summary: str


class SidebarUpdateEvent(BaseModel):
    event_type: Literal["sidebar-update"]
    data: dict[str, Any]


class DoneEvent(BaseModel):
    event_type: Literal["done"]
    dataset_id: str | None = None


class ScProgressEvent(BaseModel):
    event_type: Literal["progress"]
    flow_run_id: str
    status: str
    dataset_id: str | None = None
    imported_count: int | None = None


class ScErrorEvent(BaseModel):
    event_type: Literal["error"]
    error: str
    flow_run_id: str | None = None
    status: str | None = None


class TrainingEpochEvent(BaseModel):
    event_type: Literal["epoch"]
    job_id: str
    ts: datetime
    level: str = "info"
    message: str
    payload: dict[str, object] = Field(default_factory=dict)


class TrainingMetricEvent(BaseModel):
    event_type: Literal["metric"]
    job_id: str
    ts: datetime
    level: str = "info"
    message: str
    payload: dict[str, object] = Field(default_factory=dict)


class TrainingStatusEvent(BaseModel):
    event_type: Literal["status"]
    job_id: str
    ts: datetime
    level: str = "info"
    message: str
    payload: dict[str, object] = Field(default_factory=dict)


class TaskTrackerStateChangeEvent(BaseModel):
    event_type: Literal["state-change"]
    task: TaskTrackerDetailResponse


SSEEventPayload = Annotated[
    Union[
        AgentMessageEvent,
        AgentActionEvent,
        SidebarUpdateEvent,
        DoneEvent,
        ScProgressEvent,
        ScErrorEvent,
        TrainingEpochEvent,
        TrainingMetricEvent,
        TrainingStatusEvent,
        TaskTrackerStateChangeEvent,
    ],
    Field(discriminator="event_type"),
]


class SSEEvent(RootModel[SSEEventPayload]):
    pass
