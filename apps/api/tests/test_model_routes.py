"""Route-level tests for model endpoints.

Covers:
- GET    /models
- GET    /models/{model_id}
- DELETE /models/{model_id}
- GET    /models/{model_id}/download
"""
from __future__ import annotations

import io
import json

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import PRESET_ID

_TASK_SPEC = {"task_type": "classification", "label_space": ["cat", "dog"]}


def _create_dataset(c: TestClient) -> str:
    resp = c.post("/api/v1/datasets", json={
        "name": "model-route-ds",
        "dataset_type": "image_classification",
        "task_spec": _TASK_SPEC,
    })
    assert resp.status_code == 200
    return resp.json()["id"]


def _create_job(c: TestClient, dataset_id: str) -> str:
    resp = c.post("/api/v1/training-jobs", json={
        "dataset_id": dataset_id,
        "preset_id": PRESET_ID,
    })
    assert resp.status_code == 200
    return resp.json()["id"]


def _upload_model(c: TestClient, job_id: str) -> str:
    resp = c.post("/api/v1/models/upload", data={
        "metadata": json.dumps({
            "name": "test-model",
            "format": "pytorch",
            "job_id": job_id,
            "template_id": "image-classifier",
            "profile_id": "resnet50-cls-v1",
            "model_spec": {
                "framework": "pytorch",
                "architecture": "resnet50",
                "base_model": "torchvision/resnet50",
            },
            "compatibility": {
                "dataset_types": ["image_classification"],
                "task_types": ["classification"],
                "prediction_targets": ["image_classification"],
                "label_space": ["cat", "dog"],
            },
        }),
    }, files={"file": ("model.pt", io.BytesIO(b"fake-model-data"), "application/octet-stream")})
    assert resp.status_code == 200
    return resp.json()["id"]


def _setup(c: TestClient) -> tuple[str, str, str]:
    """Returns (dataset_id, job_id, model_id)."""
    dataset_id = _create_dataset(c)
    job_id = _create_job(c, dataset_id)
    model_id = _upload_model(c, job_id)
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
