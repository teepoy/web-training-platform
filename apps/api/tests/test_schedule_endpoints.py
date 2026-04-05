"""Integration tests for schedule API endpoints.

Mocks SchedulerService via FastAPI dependency_overrides so no real Prefect
server is required.  Uses synchronous TestClient throughout.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.services.scheduler import get_scheduler_service


# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

MOCK_DEPLOYMENT = {
    "id": "dep-uuid-1234",
    "name": "test-schedule",
    "flow_id": "flow-uuid-5678",
    "flow_name": "drain-dataset",
    "schedules": [{"schedule": {"cron": "*/5 * * * *"}, "active": True}],
    "parameters": {},
    "description": "test description",
    "paused": False,
    "created": "2026-04-01T00:00:00Z",
    "updated": "2026-04-01T00:00:00Z",
}

MOCK_RUN = {
    "id": "run-uuid-1234",
    "name": "drain-dataset-run",
    "deployment_id": "dep-uuid-1234",
    "flow_name": "drain-dataset",
    "state_type": "COMPLETED",
    "state_name": "Completed",
    "start_time": "2026-04-01T00:00:00Z",
    "end_time": "2026-04-01T00:00:05Z",
    "total_run_time": 5.0,
    "parameters": {},
}

MOCK_LOG = {
    "id": "log-uuid-1234",
    "flow_run_id": "run-uuid-1234",
    "level": 20,
    "timestamp": "2026-04-01T00:00:01Z",
    "message": "Starting drain-dataset flow",
}


# ---------------------------------------------------------------------------
# Mock service
# ---------------------------------------------------------------------------


class MockSchedulerService:
    """Async-compatible mock that returns fixture data for happy-path tests."""

    async def create_schedule(
        self, name, flow_name, cron, parameters=None, description=""
    ) -> dict:
        return MOCK_DEPLOYMENT

    async def list_schedules(self) -> list[dict]:
        return [MOCK_DEPLOYMENT]

    async def get_schedule(self, deployment_id: str) -> dict:
        return MOCK_DEPLOYMENT

    async def update_schedule(self, deployment_id: str, updates: dict) -> dict:
        return {**MOCK_DEPLOYMENT, **updates}

    async def delete_schedule(self, deployment_id: str) -> None:
        return None

    async def trigger_run(self, deployment_id: str, parameters=None) -> dict:
        return MOCK_RUN

    async def pause_schedule(self, deployment_id: str) -> dict:
        return {**MOCK_DEPLOYMENT, "paused": True}

    async def resume_schedule(self, deployment_id: str) -> dict:
        return {**MOCK_DEPLOYMENT, "paused": False}

    async def list_runs(self, deployment_id: str, limit: int = 50) -> list[dict]:
        return [MOCK_RUN]

    async def get_run(self, run_id: str) -> dict:
        return MOCK_RUN

    async def get_run_logs(self, run_id: str, limit: int = 200) -> list[dict]:
        return [MOCK_LOG]


class NotFoundSchedulerService(MockSchedulerService):
    """Raises 404 for all get/delete operations — used to test 404 propagation."""

    async def get_schedule(self, deployment_id: str) -> dict:
        raise HTTPException(status_code=404, detail="schedule not found")

    async def delete_schedule(self, deployment_id: str) -> None:
        raise HTTPException(status_code=404, detail="schedule not found")

    async def trigger_run(self, deployment_id: str, parameters=None) -> dict:
        raise HTTPException(status_code=404, detail="schedule not found")

    async def pause_schedule(self, deployment_id: str) -> dict:
        raise HTTPException(status_code=404, detail="schedule not found")

    async def resume_schedule(self, deployment_id: str) -> dict:
        raise HTTPException(status_code=404, detail="schedule not found")

    async def list_runs(self, deployment_id: str, limit: int = 50) -> list[dict]:
        raise HTTPException(status_code=404, detail="schedule not found")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    """TestClient with happy-path mock override."""

    def _get_mock():
        return MockSchedulerService()

    app.dependency_overrides[get_scheduler_service] = _get_mock
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_scheduler_service, None)


@pytest.fixture()
def not_found_client():
    """TestClient whose mock service always raises 404."""

    def _get_mock():
        return NotFoundSchedulerService()

    app.dependency_overrides[get_scheduler_service] = _get_mock
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_scheduler_service, None)


# ---------------------------------------------------------------------------
# POST /api/v1/schedules
# ---------------------------------------------------------------------------


def test_create_schedule(client: TestClient) -> None:
    r = client.post(
        "/api/v1/schedules",
        json={
            "name": "test-schedule",
            "flow_name": "drain-dataset",
            "cron": "*/5 * * * *",
            "description": "test description",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "dep-uuid-1234"
    assert body["name"] == "test-schedule"
    assert body["flow_name"] == "drain-dataset"
    assert body["cron"] == "*/5 * * * *"
    assert body["prefect_deployment_id"] == "dep-uuid-1234"
    assert "is_schedule_active" in body


# ---------------------------------------------------------------------------
# GET /api/v1/schedules
# ---------------------------------------------------------------------------


def test_list_schedules(client: TestClient) -> None:
    r = client.get("/api/v1/schedules")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["id"] == "dep-uuid-1234"


# ---------------------------------------------------------------------------
# GET /api/v1/schedules/{id}
# ---------------------------------------------------------------------------


def test_get_schedule(client: TestClient) -> None:
    r = client.get("/api/v1/schedules/dep-uuid-1234")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "dep-uuid-1234"
    assert body["name"] == "test-schedule"


# ---------------------------------------------------------------------------
# PATCH /api/v1/schedules/{id}
# ---------------------------------------------------------------------------


def test_update_schedule(client: TestClient) -> None:
    r = client.patch(
        "/api/v1/schedules/dep-uuid-1234",
        json={"description": "updated"},
    )
    assert r.status_code == 200
    body = r.json()
    # Response is still a ScheduleResponse shape
    assert body["id"] == "dep-uuid-1234"


# ---------------------------------------------------------------------------
# DELETE /api/v1/schedules/{id}
# ---------------------------------------------------------------------------


def test_delete_schedule(client: TestClient) -> None:
    r = client.delete("/api/v1/schedules/dep-uuid-1234")
    assert r.status_code == 204


# ---------------------------------------------------------------------------
# POST /api/v1/schedules/{id}/run
# ---------------------------------------------------------------------------


def test_trigger_run(client: TestClient) -> None:
    r = client.post("/api/v1/schedules/dep-uuid-1234/run")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "run-uuid-1234"
    assert body["name"] == "drain-dataset-run"
    assert body["state_type"] == "COMPLETED"


# ---------------------------------------------------------------------------
# POST /api/v1/schedules/{id}/pause
# ---------------------------------------------------------------------------


def test_pause_schedule(client: TestClient) -> None:
    r = client.post("/api/v1/schedules/dep-uuid-1234/pause")
    assert r.status_code == 200
    body = r.json()
    assert body["is_schedule_active"] is False


# ---------------------------------------------------------------------------
# POST /api/v1/schedules/{id}/resume
# ---------------------------------------------------------------------------


def test_resume_schedule(client: TestClient) -> None:
    r = client.post("/api/v1/schedules/dep-uuid-1234/resume")
    assert r.status_code == 200
    body = r.json()
    assert body["is_schedule_active"] is True


# ---------------------------------------------------------------------------
# GET /api/v1/schedules/{id}/runs
# ---------------------------------------------------------------------------


def test_list_runs(client: TestClient) -> None:
    r = client.get("/api/v1/schedules/dep-uuid-1234/runs")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["id"] == "run-uuid-1234"


# ---------------------------------------------------------------------------
# GET /api/v1/runs/{run_id}
# ---------------------------------------------------------------------------


def test_get_run(client: TestClient) -> None:
    r = client.get("/api/v1/runs/run-uuid-1234")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "run-uuid-1234"
    assert body["flow_name"] == "drain-dataset"
    assert body["state_name"] == "Completed"


# ---------------------------------------------------------------------------
# GET /api/v1/runs/{run_id}/logs
# ---------------------------------------------------------------------------


def test_get_run_logs(client: TestClient) -> None:
    r = client.get("/api/v1/runs/run-uuid-1234/logs")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 1
    log = body[0]
    assert log["id"] == "log-uuid-1234"
    assert log["level"] == 20
    assert log["message"] == "Starting drain-dataset flow"


# ---------------------------------------------------------------------------
# 404 propagation
# ---------------------------------------------------------------------------


def test_get_schedule_404(not_found_client: TestClient) -> None:
    r = not_found_client.get("/api/v1/schedules/does-not-exist")
    assert r.status_code == 404
    assert r.json()["detail"] == "schedule not found"


def test_delete_schedule_404(not_found_client: TestClient) -> None:
    r = not_found_client.delete("/api/v1/schedules/does-not-exist")
    assert r.status_code == 404


def test_trigger_run_404(not_found_client: TestClient) -> None:
    r = not_found_client.post("/api/v1/schedules/does-not-exist/run")
    assert r.status_code == 404


def test_pause_schedule_404(not_found_client: TestClient) -> None:
    r = not_found_client.post("/api/v1/schedules/does-not-exist/pause")
    assert r.status_code == 404


def test_resume_schedule_404(not_found_client: TestClient) -> None:
    r = not_found_client.post("/api/v1/schedules/does-not-exist/resume")
    assert r.status_code == 404


def test_list_runs_404(not_found_client: TestClient) -> None:
    r = not_found_client.get("/api/v1/schedules/does-not-exist/runs")
    assert r.status_code == 404
