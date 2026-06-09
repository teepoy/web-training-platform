from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.shared.api.schemas import TaskTrackerDetailResponse, TaskTrackerRawPayload, TaskTrackerDerived
from app.shared.sse.emit import emit_sse
from app.shared.sse.events import (
    AgentActionEvent,
    AgentMessageEvent,
    DoneEvent,
    ScErrorEvent,
    ScProgressEvent,
    SidebarUpdateEvent,
    SSEEvent,
    TaskTrackerStateChangeEvent,
    TrainingEpochEvent,
    TrainingMetricEvent,
    TrainingStatusEvent,
)

NOW = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def _make_task_tracker() -> TaskTrackerDetailResponse:
    return TaskTrackerDetailResponse(
        id="task-1",
        task_kind="training",
        meta={},
        raw=TaskTrackerRawPayload(),
        derived=TaskTrackerDerived(
            task_kind="training",
            execution_kind="local",
            display_status="running",
            stage="running",
        ),
    )


def test_agent_message_event_instantiation() -> None:
    e = AgentMessageEvent(event_type="agent-message", content="hello")
    assert e.event_type == "agent-message"
    assert e.content == "hello"


def test_agent_action_event_instantiation() -> None:
    e = AgentActionEvent(event_type="agent-action", tool="search", summary="searched")
    assert e.event_type == "agent-action"
    assert e.tool == "search"


def test_sidebar_update_event_instantiation() -> None:
    e = SidebarUpdateEvent(event_type="sidebar-update", data={"key": "value"})
    assert e.event_type == "sidebar-update"
    assert e.data == {"key": "value"}


def test_done_event_instantiation() -> None:
    e = DoneEvent(event_type="done")
    assert e.event_type == "done"


def test_sc_progress_event_instantiation() -> None:
    e = ScProgressEvent(event_type="progress", flow_run_id="run-1", status="running")
    assert e.event_type == "progress"
    assert e.flow_run_id == "run-1"


def test_sc_error_event_instantiation() -> None:
    e = ScErrorEvent(event_type="error", error="something failed")
    assert e.event_type == "error"
    assert e.flow_run_id is None
    assert e.status is None


def test_sc_error_event_with_optional_fields() -> None:
    e = ScErrorEvent(event_type="error", error="oops", flow_run_id="run-2", status="failed")
    assert e.flow_run_id == "run-2"
    assert e.status == "failed"


def test_training_epoch_event_instantiation() -> None:
    e = TrainingEpochEvent(event_type="epoch", job_id="job-1", ts=NOW, message="epoch done")
    assert e.event_type == "epoch"
    assert e.level == "info"
    assert e.payload == {}


def test_training_metric_event_instantiation() -> None:
    e = TrainingMetricEvent(
        event_type="metric", job_id="job-1", ts=NOW, message="acc=0.9", payload={"acc": 0.9}
    )
    assert e.event_type == "metric"
    assert e.payload == {"acc": 0.9}


def test_training_status_event_instantiation() -> None:
    e = TrainingStatusEvent(event_type="status", job_id="job-1", ts=NOW, message="started")
    assert e.event_type == "status"


def test_task_tracker_state_change_event_instantiation() -> None:
    e = TaskTrackerStateChangeEvent(event_type="state-change", task=_make_task_tracker())
    assert e.event_type == "state-change"
    assert e.task.id == "task-1"


def test_sse_event_discriminates_agent_message() -> None:
    raw = {"event_type": "agent-message", "content": "hi"}
    event = SSEEvent.model_validate(raw)
    assert isinstance(event.root, AgentMessageEvent)


def test_sse_event_discriminates_agent_action() -> None:
    raw = {"event_type": "agent-action", "tool": "grep", "summary": "found it"}
    event = SSEEvent.model_validate(raw)
    assert isinstance(event.root, AgentActionEvent)


def test_sse_event_discriminates_sidebar_update() -> None:
    raw = {"event_type": "sidebar-update", "data": {}}
    event = SSEEvent.model_validate(raw)
    assert isinstance(event.root, SidebarUpdateEvent)


def test_sse_event_discriminates_done() -> None:
    raw = {"event_type": "done"}
    event = SSEEvent.model_validate(raw)
    assert isinstance(event.root, DoneEvent)


def test_sse_event_discriminates_progress() -> None:
    raw = {"event_type": "progress", "flow_run_id": "r1", "status": "running"}
    event = SSEEvent.model_validate(raw)
    assert isinstance(event.root, ScProgressEvent)


def test_sse_event_discriminates_error() -> None:
    raw = {"event_type": "error", "error": "boom"}
    event = SSEEvent.model_validate(raw)
    assert isinstance(event.root, ScErrorEvent)


def test_sse_event_discriminates_epoch() -> None:
    raw = {"event_type": "epoch", "job_id": "j1", "ts": NOW.isoformat(), "message": "done"}
    event = SSEEvent.model_validate(raw)
    assert isinstance(event.root, TrainingEpochEvent)


def test_sse_event_discriminates_metric() -> None:
    raw = {"event_type": "metric", "job_id": "j1", "ts": NOW.isoformat(), "message": "acc"}
    event = SSEEvent.model_validate(raw)
    assert isinstance(event.root, TrainingMetricEvent)


def test_sse_event_discriminates_status() -> None:
    raw = {"event_type": "status", "job_id": "j1", "ts": NOW.isoformat(), "message": "started"}
    event = SSEEvent.model_validate(raw)
    assert isinstance(event.root, TrainingStatusEvent)


def test_sse_event_discriminates_state_change() -> None:
    task = _make_task_tracker()
    raw = {"event_type": "state-change", "task": task.model_dump()}
    event = SSEEvent.model_validate(raw)
    assert isinstance(event.root, TaskTrackerStateChangeEvent)


def test_emit_sse_format_agent_message() -> None:
    inner = AgentMessageEvent(event_type="agent-message", content="hello")
    event = SSEEvent(root=inner)
    output = emit_sse(event)
    lines = output.split("\n")
    assert lines[0] == "event: agent-message"
    assert lines[1].startswith("data: ")
    assert output.endswith("\n\n")


def test_emit_sse_data_is_valid_json() -> None:
    inner = TrainingMetricEvent(
        event_type="metric", job_id="j1", ts=NOW, message="acc=0.9", payload={"acc": 0.9}
    )
    event = SSEEvent(root=inner)
    output = emit_sse(event)
    data_line = [l for l in output.split("\n") if l.startswith("data: ")][0]
    payload = json.loads(data_line[len("data: "):])
    assert payload["event_type"] == "metric"


def test_emit_sse_event_type_in_header_matches_data() -> None:
    inner = DoneEvent(event_type="done")
    event = SSEEvent(root=inner)
    output = emit_sse(event)
    assert "event: done" in output
    data_line = [l for l in output.split("\n") if l.startswith("data: ")][0]
    payload = json.loads(data_line[len("data: "):])
    assert payload["event_type"] == "done"


def test_sse_event_json_schema_has_one_of() -> None:
    schema = SSEEvent.model_json_schema()
    schema_str = json.dumps(schema)
    assert "oneOf" in schema_str


def test_sse_event_json_schema_has_10_variants() -> None:
    schema = SSEEvent.model_json_schema()
    schema_str = json.dumps(schema)
    event_types = [
        "agent-message",
        "agent-action",
        "sidebar-update",
        "done",
        "progress",
        "error",
        "epoch",
        "metric",
        "status",
        "state-change",
    ]
    for et in event_types:
        assert et in schema_str, f"event_type '{et}' not found in JSON schema"


def test_invalid_event_type_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        SSEEvent.model_validate({"event_type": "nonexistent-event"})


def test_missing_event_type_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        SSEEvent.model_validate({"content": "hello"})


def test_wrong_fields_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        SSEEvent.model_validate({"event_type": "progress"})
