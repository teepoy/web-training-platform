from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import PRESET_ID


def _create_job(c: TestClient) -> str:
    """Create a dataset and training job; return the job_id."""
    ds = c.post(
        "/api/v1/datasets",
        json={"name": "artifact-ds", "task_spec": {"task_type": "classification", "label_space": ["a", "b"]}},
    )
    assert ds.status_code == 200
    dataset_id = ds.json()["id"]

    job = c.post(
        "/api/v1/training-jobs",
        json={"dataset_id": dataset_id, "preset_id": PRESET_ID, "created_by": "test-user"},
    )
    assert job.status_code == 200
    return job.json()["id"]


def _wait_for_completion(c: TestClient, job_id: str, timeout: float = 10.0) -> dict:
    """Poll the job until status is terminal, return final job body."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = c.get(f"/api/v1/training-jobs/{job_id}")
        assert r.status_code == 200
        body = r.json()
        if body["status"] in {"completed", "failed", "cancelled"}:
            return body
        time.sleep(0.1)
    raise TimeoutError(f"Job {job_id} did not finish within {timeout}s")


def test_download_artifact_after_job_completion() -> None:
    """After a job completes, artifact_refs should exist and be downloadable."""
    with TestClient(app) as c:
        job_id = _create_job(c)
        job_body = _wait_for_completion(c, job_id)
        assert job_body["status"] == "completed"

        artifact_refs = job_body["artifact_refs"]
        assert len(artifact_refs) > 0, "Expected at least one artifact_ref after job completion"

        artifact_id = artifact_refs[0]["id"]
        r = c.get(f"/api/v1/artifacts/{artifact_id}/download")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/octet-stream"
        # Content should be non-empty bytes (JSON metadata blob)
        assert len(r.content) > 0


def test_download_artifact_not_found() -> None:
    """Requesting a nonexistent artifact id should return 404."""
    with TestClient(app) as c:
        r = c.get("/api/v1/artifacts/nonexistent-artifact-id-99999/download")
        assert r.status_code == 404
        assert "not found" in r.json()["detail"]
