from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.modules.training.port.http.router import _training_sse_event
from app.shared.api.schemas import TrainingEvent


@pytest.mark.parametrize(
    ("level", "event_type"),
    [
        ("epoch", "epoch"),
        ("metric", "metric"),
        ("info", "status"),
        ("error", "status"),
    ],
)
def test_training_events_use_their_named_sse_channel(
    level: str,
    event_type: str,
) -> None:
    event = TrainingEvent(
        job_id="job-1",
        ts=datetime(2026, 8, 10, tzinfo=UTC),
        level=level,
        message="training update",
        payload={"epoch": 1},
    )

    encoded = _training_sse_event(event)
    payload = encoded.model_dump()

    assert encoded.root.event_type == event_type
    assert payload["job_id"] == event.job_id
    assert payload["payload"] == event.payload
