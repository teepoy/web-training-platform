from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app, container


SENSOR_ID = "dataset_size_sensor"


def _available_workflow_type(client: TestClient) -> str:
    response = client.get("/api/v1/sensors")
    assert response.status_code == 200, response.text
    sensors = response.json()
    assert sensors
    sensor = next(item for item in sensors if item["id"] == SENSOR_ID)
    return sensor["available_triggers"][0]


def _load_sensors() -> None:
    loaded = container.sensor_registry().load()
    assert loaded > 0


def _create_subscription(
    client: TestClient,
    *,
    filter_config: dict[str, object] | None = None,
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/sensors/{SENSOR_ID}/subscriptions",
        json={
            "workflow_type": _available_workflow_type(client),
            "filter_config": filter_config or {},
        },
    )
    assert response.status_code in {200, 201}, response.text
    return response.json()


def test_list_sensors_returns_dataset_size_sensor() -> None:
    _load_sensors()
    with TestClient(app) as client:
        response = client.get("/api/v1/sensors")

    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, list)
    assert any(sensor["id"] == SENSOR_ID for sensor in body)


def test_create_subscription_with_valid_workflow_type_succeeds() -> None:
    _load_sensors()
    with TestClient(app) as client:
        subscription = _create_subscription(client)

    assert subscription["sensor_id"] == SENSOR_ID
    assert subscription["workflow_type"]
    assert subscription["enabled"] is True


def test_create_subscription_with_invalid_workflow_type_returns_422() -> None:
    _load_sensors()
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/sensors/{SENSOR_ID}/subscriptions",
            json={"workflow_type": "invalid-workflow", "filter_config": {}},
        )

    assert response.status_code == 422


def test_list_subscriptions_returns_created_subscription() -> None:
    _load_sensors()
    with TestClient(app) as client:
        created = _create_subscription(client, filter_config={"dataset_id": "ds-list"})
        response = client.get(f"/api/v1/sensors/{SENSOR_ID}/subscriptions")

    assert response.status_code == 200, response.text
    subscriptions = response.json()
    assert any(subscription["id"] == created["id"] for subscription in subscriptions)


def test_update_subscription_filter_config() -> None:
    _load_sensors()
    with TestClient(app) as client:
        created = _create_subscription(client, filter_config={"dataset_id": "before"})
        response = client.patch(
            f"/api/v1/sensors/{SENSOR_ID}/subscriptions/{created['id']}",
            json={"filter_config": {"dataset_id": "after"}},
        )

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["filter_config"] == {"dataset_id": "after"}


def test_delete_subscription_removes_it() -> None:
    _load_sensors()
    with TestClient(app) as client:
        created = _create_subscription(client)
        delete_response = client.delete(
            f"/api/v1/sensors/{SENSOR_ID}/subscriptions/{created['id']}"
        )
        list_response = client.get(f"/api/v1/sensors/{SENSOR_ID}/subscriptions")

    assert delete_response.status_code == 200, delete_response.text
    assert delete_response.json() == {"deleted": True}
    assert list_response.status_code == 200, list_response.text
    assert all(
        subscription["id"] != created["id"] for subscription in list_response.json()
    )
