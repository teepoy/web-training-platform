from __future__ import annotations

from datetime import datetime, timezone

from app.shared.sse.emit import emit_sse
from app.shared.sse.events import (
    AgentActionEvent,
    AgentMessageEvent,
    DoneEvent,
    ScErrorEvent,
    ScProgressEvent,
    SSEEvent,
    SidebarUpdateEvent,
    TaskTrackerStateChangeEvent,
    TrainingEpochEvent,
    TrainingMetricEvent,
    TrainingStatusEvent,
)
from app.shared.api.schemas import (
    TaskTrackerDerived,
    TaskTrackerDetailResponse,
    TaskTrackerRawPayload,
)


def _event_cases() -> list[SSEEvent]:
    ts = datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc)
    task = TaskTrackerDetailResponse(
        id="task-1",
        task_kind="training",
        raw=TaskTrackerRawPayload(),
        derived=TaskTrackerDerived(
            task_kind="training",
            execution_kind="local",
            display_status="running",
            stage="running",
        ),
    )
    return [
        SSEEvent(AgentMessageEvent(event_type="agent-message", content="hello")),
        SSEEvent(AgentActionEvent(event_type="agent-action", tool="tool-x", summary="run")),
        SSEEvent(SidebarUpdateEvent(event_type="sidebar-update", data={"a": 1})),
        SSEEvent(DoneEvent(event_type="done")),
        SSEEvent(ScProgressEvent(event_type="progress", flow_run_id="flow-1", status="running")),
        SSEEvent(ScErrorEvent(event_type="error", error="boom", flow_run_id="flow-1", status="failed")),
        SSEEvent(
            TrainingEpochEvent(
                event_type="epoch",
                job_id="job-1",
                ts=ts,
                message="epoch done",
                payload={"epoch": 1},
            )
        ),
        SSEEvent(
            TrainingMetricEvent(
                event_type="metric",
                job_id="job-1",
                ts=ts,
                message="metric logged",
                payload={"acc": 0.9},
            )
        ),
        SSEEvent(
            TrainingStatusEvent(
                event_type="status",
                job_id="job-1",
                ts=ts,
                message="status updated",
                payload={"phase": "train"},
            )
        ),
        SSEEvent(TaskTrackerStateChangeEvent(event_type="state-change", task=task)),
    ]


def test_emit_sse_happy_path_for_each_event_type() -> None:
    for event in _event_cases():
        assert emit_sse(event) == f"event: {event.root.event_type}\ndata: {event.model_dump_json()}\n\n"


def test_emit_sse_roundtrip_parse() -> None:
    event = SSEEvent(AgentMessageEvent(event_type="agent-message", content="hello"))
    emitted = emit_sse(event)
    data_line = emitted.splitlines()[1]
    assert data_line.startswith("data: ")
    parsed = SSEEvent.model_validate_json(data_line.removeprefix("data: "))
    assert parsed == event
