from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.main import app
from app.modules.sensors.port.http.deps import get_prefect_client


SENSOR_ID = "dataset_size_sensor"


def _workflow_type(client: TestClient) -> str:
    response = client.get("/api/v1/sensors")
    assert response.status_code == 200, response.text
    sensor = next(item for item in response.json() if item["id"] == SENSOR_ID)
    return sensor["available_triggers"][0]


def _load_sensors() -> None:
    with TestClient(app):
        loaded = app.state.app_context.sensors.sensor_registry.load()
    assert loaded > 0


def _create_subscription(
    client: TestClient,
    *,
    filter_config: dict[str, object] | None = None,
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/sensors/{SENSOR_ID}/subscriptions",
        json={
            "workflow_type": _workflow_type(client),
            "filter_config": filter_config or {},
        },
    )
    assert response.status_code in {200, 201}, response.text
    return response.json()


def test_matching_event_triggers_flow_run() -> None:
    _load_sensors()
    prefect = AsyncMock()
    prefect.create_flow_run_from_deployment.return_value = {"id": "flow-run-1"}
    app.dependency_overrides[get_prefect_client] = lambda: prefect
    try:
        with TestClient(app) as client:
            _create_subscription(client, filter_config={"dataset_id": "ds-match"})
            response = client.post(
                "/api/v1/sensors/events",
                json={
                    "sensor_id": SENSOR_ID,
                    "events": [{"dataset_id": "ds-match", "sample_count": 3}],
                },
            )
    finally:
        app.dependency_overrides.pop(get_prefect_client, None)

    assert response.status_code == 200, response.text
    assert response.json()["triggered"] == 1
    prefect.create_flow_run_from_deployment.assert_awaited_once()


def test_non_matching_filter_does_not_trigger_flow_run() -> None:
    _load_sensors()
    prefect = AsyncMock()
    prefect.create_flow_run_from_deployment.return_value = {"id": "flow-run-1"}
    app.dependency_overrides[get_prefect_client] = lambda: prefect
    try:
        with TestClient(app) as client:
            _create_subscription(client, filter_config={"dataset_id": "ds-match"})
            response = client.post(
                "/api/v1/sensors/events",
                json={
                    "sensor_id": SENSOR_ID,
                    "events": [{"dataset_id": "ds-other", "sample_count": 3}],
                },
            )
    finally:
        app.dependency_overrides.pop(get_prefect_client, None)

    assert response.status_code == 200, response.text
    assert response.json()["triggered"] == 0
    prefect.create_flow_run_from_deployment.assert_not_awaited()


def test_failing_subscription_dispatch_does_not_abort_others() -> None:
    _load_sensors()
    prefect = AsyncMock()
    prefect.create_flow_run_from_deployment.side_effect = [
        RuntimeError("prefect failed"),
        {"id": "flow-run-2"},
    ]
    app.dependency_overrides[get_prefect_client] = lambda: prefect
    try:
        with TestClient(app) as client:
            _create_subscription(client, filter_config={"dataset_id": "ds-shared"})
            _create_subscription(client, filter_config={"dataset_id": "ds-shared"})
            response = client.post(
                "/api/v1/sensors/events",
                json={
                    "sensor_id": SENSOR_ID,
                    "events": [{"dataset_id": "ds-shared", "sample_count": 9}],
                },
            )
    finally:
        app.dependency_overrides.pop(get_prefect_client, None)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["errors"] == 1
    assert body["triggered"] == 1
    assert prefect.create_flow_run_from_deployment.await_count == 2


def test_event_post_updates_checkpoint_and_subscriptions_remain_readable() -> None:
    _load_sensors()
    prefect = AsyncMock()
    prefect.create_flow_run_from_deployment.return_value = {"id": "flow-run-1"}
    app.dependency_overrides[get_prefect_client] = lambda: prefect
    try:
        with TestClient(app) as client:
            created = _create_subscription(client, filter_config={"dataset_id": "ds-checkpoint"})
            event_response = client.post(
                "/api/v1/sensors/events",
                json={
                    "sensor_id": SENSOR_ID,
                    "events": [{"dataset_id": "ds-checkpoint", "sample_count": 5}],
                    "watermark": {"checked_at": "2026-05-16T00:00:00+00:00"},
                },
            )
            list_response = client.get(f"/api/v1/sensors/{SENSOR_ID}/subscriptions")
    finally:
        app.dependency_overrides.pop(get_prefect_client, None)

    assert event_response.status_code == 200, event_response.text
    assert list_response.status_code == 200, list_response.text
    assert any(
        subscription["id"] == created["id"] for subscription in list_response.json()
    )
