"""Tests for the dashboard endpoint (GET /api/v1/dashboard).

The test profile uses mocked or unavailable infra dependencies, so the dashboard
may report degraded/down service states while still returning queue aggregates.
These tests validate the response shape without requiring a live Prefect server.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.main import app
from app.core.config import load_config
from app.modules.dashboard.app.services.service_health import ServiceHealthService
from app.modules.dashboard.port.http.deps import get_prefect_client, get_repository, get_service_health
from tests.conftest import TRAINER_ID


def _create_job(c: TestClient) -> str:
    """Helper: create a dataset + job, return job_id."""
    ds = c.post(
        "/api/v1/datasets",
        json={"name": "dash-ds", "task_spec": {"task_type": "classification", "label_space": ["a"]}},
    )
    dataset_id = ds.json()["id"]
    job = c.post(
        "/api/v1/training-jobs",
        json={"dataset_id": dataset_id, "trainer_id": TRAINER_ID, "created_by": "tester"},
    )
    return job.json()["id"]


def test_dashboard_empty() -> None:
    """Dashboard returns valid shape even with no jobs."""
    with TestClient(app) as c:
        r = c.get("/api/v1/dashboard")
        assert r.status_code == 200
        body = r.json()
        assert "job_queue" in body
        assert "recent_jobs" in body
        assert "services" in body
        assert isinstance(body["recent_jobs"], list)
        assert isinstance(body["services"], list)
        assert body["prefect_connected"] is False
        assert body["work_pool"] is None
        # Job queue stats should all be zero-ish (may inherit from other tests)
        for key in ("queued", "running", "completed", "failed", "cancelled"):
            assert key in body["job_queue"]


def test_dashboard_response_shape() -> None:
    """Validate the full response schema."""
    with TestClient(app) as c:
        r = c.get("/api/v1/dashboard")
        assert r.status_code == 200
        body = r.json()

        # Top-level keys
        assert set(body.keys()) == {"work_pool", "job_queue", "recent_jobs", "services", "prefect_connected"}

        # job_queue keys
        assert set(body["job_queue"].keys()) == {"queued", "running", "completed", "failed", "cancelled"}

        # Each recent job has the expected fields
        for job in body["recent_jobs"]:
            for field in ("id", "dataset_id", "trainer_id", "status", "created_by", "created_at", "updated_at"):
                assert field in job

        for service in body["services"]:
            for field in ("name", "kind", "status", "detail", "latency_ms", "endpoint"):
                assert field in service


def test_dashboard_reports_prefect_worker_down_when_no_work_queues() -> None:
    prefect_client = AsyncMock()
    prefect_client.get_work_pool.side_effect = lambda name: {"name": name}
    prefect_client.list_work_queues.side_effect = Exception("no work queues available")
    service_health = ServiceHealthService(
        config=load_config(),
        prefect_client=prefect_client,
    )
    job_repository = AsyncMock()
    job_repository.list_jobs.return_value = []
    try:
        with TestClient(app) as c:
            app.dependency_overrides[get_repository] = lambda: job_repository
            app.dependency_overrides[get_service_health] = lambda: service_health
            app.dependency_overrides[get_prefect_client] = lambda: prefect_client
            r = c.get("/api/v1/dashboard")
        assert r.status_code == 200
        services = {service["name"]: service for service in r.json()["services"]}
        assert services["prefect-worker"]["status"] == "down"
        assert "no work queues available" in services["prefect-worker"]["detail"]
    finally:
        app.dependency_overrides.pop(get_repository, None)
        app.dependency_overrides.pop(get_service_health, None)
        app.dependency_overrides.pop(get_prefect_client, None)


def test_dashboard_reports_prefect_worker_healthy_when_work_queues_exist() -> None:
    prefect_client = AsyncMock()
    prefect_client.get_work_pool.side_effect = lambda name: {"name": name}
    prefect_client.list_work_queues.side_effect = lambda _work_pool_name: [{"name": "default"}]
    service_health = ServiceHealthService(
        config=load_config(),
        prefect_client=prefect_client,
    )
    job_repository = AsyncMock()
    job_repository.list_jobs.return_value = []
    try:
        with TestClient(app) as c:
            app.dependency_overrides[get_repository] = lambda: job_repository
            app.dependency_overrides[get_service_health] = lambda: service_health
            app.dependency_overrides[get_prefect_client] = lambda: prefect_client
            r = c.get("/api/v1/dashboard")
        assert r.status_code == 200
        services = {service["name"]: service for service in r.json()["services"]}
        assert services["prefect-worker"]["status"] == "healthy"
        assert "1 work queue(s)" in services["prefect-worker"]["detail"]
    finally:
        app.dependency_overrides.pop(get_repository, None)
        app.dependency_overrides.pop(get_service_health, None)
        app.dependency_overrides.pop(get_prefect_client, None)
