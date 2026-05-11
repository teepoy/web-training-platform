"""Route-level tests for model endpoints.

Covers:
- GET    /models
- GET    /models/{model_id}
- DELETE /models/{model_id}
- GET    /models/{model_id}/download
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import create_dataset, create_job, upload_model


def _setup(c: TestClient) -> tuple[str, str, str]:
    """Returns (dataset_id, job_id, model_id)."""
    dataset_id = create_dataset(c)
    job_id = create_job(c, dataset_id)
    model_id = upload_model(c, job_id)
    return dataset_id, job_id, model_id


# ---------------------------------------------------------------------------
# List models
# ---------------------------------------------------------------------------

def test_list_models_empty() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/models")
        assert resp.status_code == 200
        assert resp.json() == []


def test_list_models() -> None:
    with TestClient(app) as c:
        dataset_id, job_id, model_id = _setup(c)
        resp = c.get("/api/v1/models")
        assert resp.status_code == 200
        models = resp.json()
        assert len(models) >= 1
        assert any(m["id"] == model_id for m in models)


def test_list_models_filter_by_dataset() -> None:
    with TestClient(app) as c:
        dataset_id, job_id, model_id = _setup(c)
        resp = c.get("/api/v1/models", params={"dataset_id": dataset_id})
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

        # Non-existent dataset should return empty
        resp2 = c.get("/api/v1/models", params={"dataset_id": "nonexistent"})
        assert resp2.status_code == 200
        assert resp2.json() == []


def test_list_models_filter_by_job() -> None:
    with TestClient(app) as c:
        dataset_id, job_id, model_id = _setup(c)
        resp = c.get("/api/v1/models", params={"job_id": job_id})
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


# ---------------------------------------------------------------------------
# Get model
# ---------------------------------------------------------------------------

def test_get_model() -> None:
    with TestClient(app) as c:
        _ds, _job, model_id = _setup(c)
        resp = c.get(f"/api/v1/models/{model_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == model_id
        assert body["name"] == "test-model"


def test_get_model_not_found() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/models/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Download model
# ---------------------------------------------------------------------------

def test_download_model() -> None:
    with TestClient(app) as c:
        _ds, _job, model_id = _setup(c)
        resp = c.get(f"/api/v1/models/{model_id}/download")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/octet-stream"
        assert len(resp.content) > 0


def test_download_model_not_found() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/models/nonexistent/download")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete model
# ---------------------------------------------------------------------------

def test_delete_model() -> None:
    with TestClient(app) as c:
        _ds, _job, model_id = _setup(c)
        resp = c.delete(f"/api/v1/models/{model_id}")
        assert resp.status_code == 204

        # Verify it's gone
        get_resp = c.get(f"/api/v1/models/{model_id}")
        assert get_resp.status_code == 404


def test_delete_model_not_found() -> None:
    with TestClient(app) as c:
        resp = c.delete("/api/v1/models/nonexistent")
        assert resp.status_code == 404
