from __future__ import annotations

import json

import pytest

from app.modules.sc.data_provider.router import (
    _invalidation_from_message,
    _sse_event,
)
from app.modules.sc.data_provider.schemas import ScDataInvalidationEvent
from app.modules.sc.data_provider.scope import ScDataScope
from app.shared.infrastructure.redis.event_publisher import PREDICTION_CHANNEL


def test_dataset_event_maps_atomic_revision_and_changed_kind() -> None:
    scope = ScDataScope.dataset(dataset_id="ds-1", org_id="org-1")
    event = _invalidation_from_message(
        scope,
        {
            "channel": PREDICTION_CHANNEL.encode(),
            "data": json.dumps(
                {
                    "revision": 7,
                    "event": "prediction.refresh",
                    "data": {"dataset_id": "ds-1"},
                }
            ).encode(),
        },
    )

    assert event == ScDataInvalidationEvent(
        scope="dataset:ds-1",
        revision=7,
        changed_kinds=["prediction"],
    )
    assert event is not None
    assert _sse_event(event).startswith("event: invalidation\ndata: {")


@pytest.mark.parametrize("wafer_key", [None, "invalid", [], {}])
def test_malformed_inspection_event_is_ignored(wafer_key: object) -> None:
    scope = ScDataScope.inspection(
        inspection_time="2026-01-01T00:00:00",
        wafer_key=3,
        org_id="org-1",
    )

    assert (
        _invalidation_from_message(
            scope,
            {
                "channel": PREDICTION_CHANNEL,
                "data": json.dumps(
                    {
                        "revision": 1,
                        "data": {
                            "inspection_time": "2026-01-01T00:00:00",
                            "wafer_key": wafer_key,
                        },
                    }
                ),
            },
        )
        is None
    )
