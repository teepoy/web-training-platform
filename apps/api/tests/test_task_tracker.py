from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import PRESET_ID


def _create_dataset(client: TestClient, name: str) -> str:
    response = client.post(
        "/api/v1/datasets",
        json={"name": name, "task_spec": {"task_type": "classification", "label_space": ["a", "b"]}},
    )
    response.raise_for_status()
    return response.json()["id"]


def test_task_tracker_lists_training_and_prediction_jobs() -> None:
    with TestClient(app) as client:
        dataset_id = _create_dataset(client, "tracker-ds")
        training = client.post(
            "/api/v1/training-jobs",
            json={"dataset_id": dataset_id, "preset_id": PRESET_ID},
        )
        assert training.status_code == 200

        prediction = client.post(f"/api/v1/datasets/{dataset_id}/features/extract")
        assert prediction.status_code == 200

        listing = client.get("/api/v1/task-tracker/tasks")
        assert listing.status_code == 200
        body = listing.json()
        assert len(body) >= 2
        kinds = {item["task_kind"] for item in body}
        assert "training" in kinds
        assert "prediction" in kinds


def test_task_tracker_detail_contains_raw_and_derived() -> None:
    with TestClient(app) as client:
        dataset_id = _create_dataset(client, "tracker-detail")
        training = client.post(
            "/api/v1/training-jobs",
            json={"dataset_id": dataset_id, "preset_id": PRESET_ID},
        )
        training.raise_for_status()
        task_id = training.json()["id"]

        detail = client.get(f"/api/v1/task-tracker/tasks/{task_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["id"] == task_id
        assert body["task_kind"] == "training"
        assert "raw" in body
        assert "derived" in body
        assert "platform_job" in body["raw"]
        assert "stages" in body["derived"]
        assert "scorecard" in body["derived"]


def test_task_tracker_filters_by_kind() -> None:
    with TestClient(app) as client:
        dataset_id = _create_dataset(client, "tracker-filter")
        client.post(
            "/api/v1/training-jobs",
            json={"dataset_id": dataset_id, "preset_id": PRESET_ID},
        ).raise_for_status()

        prediction = client.post(f"/api/v1/datasets/{dataset_id}/features/extract")
        assert prediction.status_code == 200

        listing = client.get("/api/v1/task-tracker/tasks?kind=prediction")
        assert listing.status_code == 200
        body = listing.json()
        assert body
        assert all(item["task_kind"] == "prediction" for item in body)


def test_task_tracker_stream_returns_snapshot_events() -> None:
    with TestClient(app) as client:
        dataset_id = _create_dataset(client, "tracker-stream")
        training = client.post(
            "/api/v1/training-jobs",
            json={"dataset_id": dataset_id, "preset_id": PRESET_ID},
        )
        training.raise_for_status()
        task_id = training.json()["id"]

        with client.stream("GET", f"/api/v1/task-tracker/tasks/{task_id}/stream") as response:
            assert response.status_code == 200
            chunks = []
            for chunk in response.iter_text():
                if chunk:
                    chunks.append(chunk)
                if any("data: " in part for part in chunks):
                    break

        joined = "".join(chunks)
        assert 'data: ' in joined
        assert task_id in joined


def test_task_tracker_lists_schedule_runs() -> None:
    with TestClient(app) as client:
        create = client.post(
            "/api/v1/schedules",
            json={
                "name": "tracker-schedule",
                "flow_name": "drain-dataset",
                "cron": "*/5 * * * *",
                "description": "tracker schedule",
            },
        )
        create.raise_for_status()
        schedule_id = create.json()["id"]

        trigger = client.post(f"/api/v1/schedules/{schedule_id}/run")
        assert trigger.status_code == 200

        listing = client.get("/api/v1/task-tracker/tasks?kind=schedule_run")
        assert listing.status_code == 200
        body = listing.json()
        assert body
        assert all(item["task_kind"] == "schedule_run" for item in body)
