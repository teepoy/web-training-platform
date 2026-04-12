from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from dependency_injector import providers
from fastapi.testclient import TestClient

from app.main import app
from app.services.task_tracker import TaskTrackerService
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


def test_task_tracker_detail_uses_prefect_task_runs_for_execution_flow() -> None:
    prefect = SimpleNamespace(
        get_flow_run=AsyncMock(return_value={
            "id": "flow-run-1",
            "deployment_id": "deployment-1",
            "work_pool_name": "training-pool",
            "work_queue_name": "train-gpu",
            "state": {"type": "RUNNING", "name": "Running"},
        }),
        get_deployment=AsyncMock(return_value={"id": "deployment-1"}),
        get_work_queue_by_name=AsyncMock(return_value={"priority": 1}),
        get_work_pool=AsyncMock(return_value={"concurrency_limit": 4, "status": {"slots_used": 2}}),
        get_flow_run_logs=AsyncMock(return_value=[]),
        list_task_runs=AsyncMock(return_value=[
            {
                "id": "task-run-prepare",
                "name": "prepare_dataset",
                "state": {"type": "COMPLETED", "name": "Completed"},
                "start_time": "2026-04-11T10:00:00Z",
                "end_time": "2026-04-11T10:01:00Z",
            },
            {
                "id": "task-run-train",
                "name": "train_model",
                "state": {"type": "RUNNING", "name": "Running"},
                "start_time": "2026-04-11T10:01:05Z",
            },
        ]),
        filter_flow_runs=AsyncMock(return_value=[]),
    )

    with TestClient(app) as client:
        from app.main import container

        container.prefect_client.override(providers.Object(prefect))
        try:
            dataset_id = _create_dataset(client, "tracker-dynamic-flow")
            training = client.post(
                "/api/v1/training-jobs",
                json={"dataset_id": dataset_id, "preset_id": PRESET_ID},
            )
            training.raise_for_status()
            task_id = training.json()["id"]
            asyncio.run(container.repository().set_job_external_id(task_id, "flow-run-1"))

            detail = client.get(f"/api/v1/task-tracker/tasks/{task_id}")
            assert detail.status_code == 200
            body = detail.json()
            execution_flow = next(stage for stage in body["derived"]["stages"] if stage["key"] == "execution_flow")
            assert [node["label"] for node in execution_flow["nodes"]] == ["prepare_dataset", "train_model"]
            assert execution_flow["nodes"][0]["status"] == "completed"
            assert execution_flow["nodes"][1]["status"] == "active"
            assert execution_flow["nodes"][0]["started_at"] == "2026-04-11T10:00:00Z"
            assert execution_flow["nodes"][0]["ended_at"] == "2026-04-11T10:01:00Z"
            assert body["derived"]["deep_links"]["prefect_run_url"] == "http://localhost:4200/runs/flow-run/flow-run-1"
        finally:
            container.prefect_client.reset_override()


def test_prefect_run_url_strips_api_v1_suffix() -> None:
    service = TaskTrackerService(
        repository=SimpleNamespace(),
        prefect_client=SimpleNamespace(),
        config=SimpleNamespace(prefect=SimpleNamespace(api_url="http://prefect.example/api/v1")),
    )

    assert service._prefect_ui_base_url() == "http://prefect.example"


def test_prefect_run_url_prefers_explicit_ui_url() -> None:
    service = TaskTrackerService(
        repository=SimpleNamespace(),
        prefect_client=SimpleNamespace(),
        config=SimpleNamespace(prefect=SimpleNamespace(api_url="http://prefect-server:4200/api", ui_url="http://localhost:4200")),
    )

    assert service._prefect_ui_base_url() == "http://localhost:4200"
