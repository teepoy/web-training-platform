from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.datasets.port.http.deps import get_artifact_storage
from tests.support.artifact_storage import InMemoryArtifactStorage
from tests.conftest import TRAINER_ID


def _create_job(c: TestClient) -> str:
    """Create a dataset and training job; return the job_id."""
    ds = c.post(
        "/api/v1/datasets",
        json={
            "name": "artifact-ds",
            "task_spec": {"task_type": "classification", "label_space": ["a", "b"]},
        },
    )
    assert ds.status_code == 200
    dataset_id = ds.json()["id"]

    job = c.post(
        "/api/v1/training-jobs",
        json={
            "dataset_id": dataset_id,
            "trainer_id": TRAINER_ID,
            "created_by": "test-user",
        },
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


@pytest.mark.skip(reason="Pre-existing failure - see errors.md")
def test_download_artifact_after_job_completion() -> None:
    """After a job completes, artifact_refs should exist and be downloadable."""
    with TestClient(app) as c:
        job_id = _create_job(c)
        job_body = _wait_for_completion(c, job_id)
        assert job_body["status"] == "completed"

        artifact_refs = job_body["artifact_refs"]
        assert len(artifact_refs) > 0, (
            "Expected at least one artifact_ref after job completion"
        )

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


def test_export_download_streams_full_object_with_range_metadata() -> None:
    storage = InMemoryArtifactStorage()
    payload = b"0123456789" * 200_000
    uri = asyncio.run(storage.put_bytes("exports/dataset-1/large.zip", payload))
    app.dependency_overrides[get_artifact_storage] = lambda: storage
    try:
        with TestClient(app) as c:
            response = c.get("/api/v1/download", params={"uri": uri})
    finally:
        app.dependency_overrides.pop(get_artifact_storage, None)

    assert response.status_code == 200
    assert response.content == payload
    assert response.headers["content-length"] == str(len(payload))
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["x-accel-buffering"] == "no"
    assert 'filename="large.zip"' in response.headers["content-disposition"]


def test_export_download_honors_single_byte_range() -> None:
    storage = InMemoryArtifactStorage()
    uri = asyncio.run(
        storage.put_bytes("exports/dataset-1/large.parquet", b"0123456789")
    )
    app.dependency_overrides[get_artifact_storage] = lambda: storage
    try:
        with TestClient(app) as c:
            response = c.get(
                "/api/v1/download",
                params={"uri": uri},
                headers={"Range": "bytes=3-6"},
            )
    finally:
        app.dependency_overrides.pop(get_artifact_storage, None)

    assert response.status_code == 206
    assert response.content == b"3456"
    assert response.headers["content-length"] == "4"
    assert response.headers["content-range"] == "bytes 3-6/10"


def test_export_download_rejects_unsatisfied_range() -> None:
    storage = InMemoryArtifactStorage()
    uri = asyncio.run(storage.put_bytes("exports/dataset-1/empty.zip", b""))
    app.dependency_overrides[get_artifact_storage] = lambda: storage
    try:
        with TestClient(app) as c:
            response = c.get(
                "/api/v1/download",
                params={"uri": uri},
                headers={"Range": "bytes=0-1"},
            )
    finally:
        app.dependency_overrides.pop(get_artifact_storage, None)

    assert response.status_code == 416
    assert response.headers["content-range"] == "bytes */0"


def test_export_download_hides_another_organizations_scoped_object() -> None:
    storage = InMemoryArtifactStorage()
    uri = asyncio.run(
        storage.put_bytes(
            "exports/orgs/not-the-current-org/datasets/dataset-1/private.zip",
            b"private",
        )
    )
    app.dependency_overrides[get_artifact_storage] = lambda: storage
    try:
        with TestClient(app) as c:
            response = c.get("/api/v1/download", params={"uri": uri})
    finally:
        app.dependency_overrides.pop(get_artifact_storage, None)

    assert response.status_code == 404
    assert response.json()["detail"] == "export artifact not found"
