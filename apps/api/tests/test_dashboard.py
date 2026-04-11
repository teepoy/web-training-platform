"""Tests for the dashboard endpoint (GET /api/v1/dashboard).

The test profile uses mocked or unavailable infra dependencies, so the dashboard
may report degraded/down service states while still returning queue aggregates.
These tests validate the response shape without requiring a live Prefect server.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import PRESET_ID


def _create_job(c: TestClient) -> str:
    """Helper: create a dataset + job, return job_id."""
    ds = c.post(
        "/api/v1/datasets",
        json={"name": "dash-ds", "task_spec": {"task_type": "classification", "label_space": ["a"]}},
    )
    dataset_id = ds.json()["id"]
    job = c.post(
        "/api/v1/training-jobs",
        json={"dataset_id": dataset_id, "preset_id": PRESET_ID, "created_by": "tester"},
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


def test_dashboard_with_jobs() -> None:
    """Dashboard reflects created jobs in queue stats and recent list."""
    with TestClient(app) as c:
        job_id = _create_job(c)

        r = c.get("/api/v1/dashboard")
        assert r.status_code == 200
        body = r.json()

        # At least one job should show up in recent_jobs
        ids = [j["id"] for j in body["recent_jobs"]]
        assert job_id in ids

        # Total count across all statuses should be >= 1
        jq = body["job_queue"]
        total = jq["queued"] + jq["running"] + jq["completed"] + jq["failed"] + jq["cancelled"]
        assert total >= 1


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
            for field in ("id", "dataset_id", "preset_id", "status", "created_by", "created_at", "updated_at"):
                assert field in job

        for service in body["services"]:
            for field in ("name", "kind", "status", "detail", "latency_ms", "endpoint"):
                assert field in service
