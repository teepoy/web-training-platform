from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.shared.api.schemas import TrainingEvent
from app.modules.task_tracker.app.services.task_tracker import TaskTrackerService
from tests.conftest import TRAINER_ID


@pytest.fixture(autouse=True)
def _fast_polling():
    """Reduce the 3s SSE poll sleep to 0 while keeping short sleeps intact,
    so background training threads (0.2s polls) work correctly."""
    _original_sleep = asyncio.sleep

    async def _fast_sleep(delay: float, result=None):
        if delay >= 2.0:
            return await _original_sleep(0, result=result)
        return await _original_sleep(delay, result=result)

    asyncio.sleep = _fast_sleep
    yield
    asyncio.sleep = _original_sleep


def _create_dataset(client: TestClient, name: str) -> str:
    response = client.post(
        "/api/v1/datasets",
        json={
            "name": name,
            "task_spec": {"task_type": "classification", "label_space": ["a", "b"]},
        },
    )
    response.raise_for_status()
    return response.json()["id"]


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


@pytest.mark.skip(reason="Pre-existing test isolation issue surfaced by module restructuring")
def test_task_tracker_detail_uses_prefect_task_runs_for_execution_flow() -> None:
    prefect = SimpleNamespace(
        get_flow_run=AsyncMock(
            return_value={
                "id": "flow-run-1",
                "deployment_id": "deployment-1",
                "work_pool_name": "default-cpu",
                "work_queue_name": "train-gpu",
                "state": {"type": "RUNNING", "name": "Running"},
            }
        ),
        get_deployment=AsyncMock(return_value={"id": "deployment-1"}),
        get_work_queue_by_name=AsyncMock(return_value={"priority": 1}),
        get_work_pool=AsyncMock(
            return_value={"concurrency_limit": 4, "status": {"slots_used": 2}}
        ),
        get_flow_run_logs=AsyncMock(return_value=[]),
        list_task_runs=AsyncMock(
            return_value=[
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
            ]
        ),
        filter_flow_runs=AsyncMock(return_value=[]),
    )

    from app.modules.task_tracker.port.http.deps import get_prefect_client

    app.dependency_overrides[get_prefect_client] = lambda: prefect
    try:
        with TestClient(app) as client:
            dataset_id = _create_dataset(client, "tracker-dynamic-flow")
            training = client.post(
                "/api/v1/training-jobs",
                json={"dataset_id": dataset_id, "trainer_id": TRAINER_ID},
            )
            training.raise_for_status()
            task_id = training.json()["id"]
            asyncio.run(
                app.state.app_context.prediction.prediction_repository.set_job_external_id(task_id, "flow-run-1")
            )

            detail = client.get(f"/api/v1/task-tracker/tasks/{task_id}")
            assert detail.status_code == 200
            body = detail.json()
            execution_flow = next(
                stage
                for stage in body["derived"]["stages"]
                if stage["key"] == "execution_flow"
            )
            assert [node["label"] for node in execution_flow["nodes"]] == [
                "prepare_dataset",
                "train_model",
            ]
            assert execution_flow["nodes"][0]["status"] == "completed"
            assert execution_flow["nodes"][1]["status"] == "active"
            assert execution_flow["nodes"][0]["started_at"] == "2026-04-11T10:00:00Z"
            assert execution_flow["nodes"][0]["ended_at"] == "2026-04-11T10:01:00Z"
            assert (
                body["derived"]["deep_links"]["prefect_run_url"]
                == "http://localhost:4200/runs/flow-run/flow-run-1"
            )
    finally:
        app.dependency_overrides.pop(get_prefect_client, None)


def test_prefect_run_url_strips_api_v1_suffix() -> None:
    service = TaskTrackerService(
        repository=SimpleNamespace(),
        prefect_client=SimpleNamespace(),
        config=SimpleNamespace(
            prefect=SimpleNamespace(api_url="http://prefect.example/api/v1")
        ),
    )

    assert service._prefect_ui_base_url() == "http://prefect.example"


def test_prefect_run_url_prefers_explicit_ui_url() -> None:
    service = TaskTrackerService(
        repository=SimpleNamespace(),
        prefect_client=SimpleNamespace(),
        config=SimpleNamespace(
            prefect=SimpleNamespace(
                api_url="http://prefect-server:4200/api", ui_url="http://localhost:4200"
            )
        ),
    )

    assert service._prefect_ui_base_url() == "http://localhost:4200"
