"""Tests for the dashboard endpoint (GET /api/v1/dashboard).

The local-smoke profile uses ``execution.engine: local`` so the dashboard
will report ``prefect_connected=False`` and ``work_pool=None``.  These tests
validate the job-queue aggregation and recent-jobs listing without needing
a live Prefect server.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def _create_job(c: TestClient) -> str:
    """Helper: create a dataset + preset + job, return job_id."""
    ds = c.post(
        "/api/v1/datasets",
        json={"name": "dash-ds", "task_spec": {"task_type": "classification", "label_space": ["a"]}},
    )
    dataset_id = ds.json()["id"]
    pr = c.post(
        "/api/v1/training-presets",
        json={
            "name": "dash-preset",
            "model_spec": {"framework": "pytorch", "base_model": "resnet18"},
            "omegaconf_yaml": "trainer:\n  max_epochs: 1",
            "dataloader_ref": "ref",
        },
    )
    preset_id = pr.json()["id"]
    job = c.post(
        "/api/v1/training-jobs",
        json={"dataset_id": dataset_id, "preset_id": preset_id, "created_by": "tester"},
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
        assert isinstance(body["recent_jobs"], list)
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
        assert set(body.keys()) == {"work_pool", "job_queue", "recent_jobs", "prefect_connected"}

        # job_queue keys
        assert set(body["job_queue"].keys()) == {"queued", "running", "completed", "failed", "cancelled"}

        # Each recent job has the expected fields
        for job in body["recent_jobs"]:
            for field in ("id", "dataset_id", "preset_id", "status", "created_by", "created_at", "updated_at"):
                assert field in job
