from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch


class _FakeResponse:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> object:
        return self._payload

    def raise_for_status(self) -> None:
        return None


class _FakeAsyncClient:
    def __init__(self, *, get_payload: object | None = None) -> None:
        self.get_payload = get_payload or []
        self.post_calls: list[dict[str, Any]] = []

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def get(self, url: str) -> _FakeResponse:
        return _FakeResponse(self.get_payload)

    async def post(self, url: str, json: dict[str, Any]) -> _FakeResponse:
        self.post_calls.append({"url": url, "json": json})
        return _FakeResponse({"dispatched": len(json["events"]), "triggered": 0, "errors": 0})


def test_dataset_size_sensor_posts_event_batch_for_changed_counts() -> None:
    from app.modules.jobs.sensors.adapter.flows import dataset_size_sensor as flow_module

    client = _FakeAsyncClient(
        get_payload=[
            {"id": "dataset-1", "sample_count": 3},
            {"id": "dataset-2", "sample_count": 7},
        ]
    )

    with (
        patch.object(flow_module.httpx, "AsyncClient", return_value=client),
        patch.object(flow_module, "get_run_logger", return_value=MagicMock()),
        patch.object(
            flow_module,
            "fetch_dataset_sizes",
            side_effect=flow_module.fetch_dataset_sizes.fn,
        ),
    ):
        result = asyncio.run(flow_module.dataset_size_sensor.fn())

    assert result["event_count"] == 2
    assert len(client.post_calls) == 1
    payload = client.post_calls[0]["json"]
    assert client.post_calls[0]["url"] == flow_module.SENSOR_EVENTS_URL
    assert payload["sensor_id"] == "dataset_size_sensor"
    assert payload["events"] == [
        {"dataset_id": "dataset-1", "sample_count": 3},
        {"dataset_id": "dataset-2", "sample_count": 7},
    ]
    assert "checked_at" in payload["watermark"]


def test_dataset_size_sensor_posts_empty_event_batch_when_counts_unchanged() -> None:
    from app.modules.jobs.sensors.adapter.flows import dataset_size_sensor as flow_module

    client = _FakeAsyncClient()
    fetch_dataset_sizes = AsyncMock(return_value=[])

    with (
        patch.object(flow_module.httpx, "AsyncClient", return_value=client),
        patch.object(flow_module, "get_run_logger", return_value=MagicMock()),
        patch.object(flow_module, "fetch_dataset_sizes", fetch_dataset_sizes),
    ):
        result = asyncio.run(flow_module.dataset_size_sensor.fn())

    assert result["event_count"] == 0
    assert len(client.post_calls) == 1
    assert client.post_calls[0]["json"]["events"] == []
