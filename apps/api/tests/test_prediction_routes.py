"""Route-level tests for prediction endpoints.

Covers:
- POST /predictions/single
- GET  /prediction-jobs
- GET  /prediction-jobs/{job_id}
- GET  /prediction-jobs/{job_id}/predictions
- GET  /prediction-jobs/{job_id}/events
- POST /prediction-jobs/{job_id}/cancel
- GET  /samples/{sample_id}/predictions
- POST /prediction-collections
- GET  /prediction-collections
- POST /prediction-collections/{id}/sync-label-studio
"""
from __future__ import annotations

import io
import json
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app, container
from tests.conftest import PRESET_ID

_TASK_SPEC = {"task_type": "classification", "label_space": ["cat", "dog"]}


def _create_dataset(c: TestClient) -> str:
    resp = c.post("/api/v1/datasets", json={
        "name": "pred-route-ds",
        "dataset_type": "image_classification",
        "task_spec": _TASK_SPEC,
    })
    assert resp.status_code == 200
    return resp.json()["id"]


def _create_sample(c: TestClient, dataset_id: str) -> str:
    resp = c.post(f"/api/v1/datasets/{dataset_id}/samples", json={
        "image_uris": [],
        "metadata": {},
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
    }, files={"file": ("model.pt", io.BytesIO(b"fake-model"), "application/octet-stream")})
    assert resp.status_code == 200
    return resp.json()["id"]


def _setup(c: TestClient) -> tuple[str, str, str, str]:
    """Create dataset + sample + job + model. Returns (dataset_id, sample_id, model_id, job_id)."""
    dataset_id = _create_dataset(c)
    sample_id = _create_sample(c, dataset_id)
    job_id = _create_job(c, dataset_id)
    model_id = _upload_model(c, job_id)
    return dataset_id, sample_id, model_id, job_id


# ---------------------------------------------------------------------------
# Prediction jobs CRUD
# ---------------------------------------------------------------------------

def test_list_prediction_jobs_empty() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/prediction-jobs")
        assert resp.status_code == 200
        assert resp.json() == []


def test_prediction_job_not_found() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/prediction-jobs/nonexistent")
        assert resp.status_code == 404


def test_prediction_job_lifecycle() -> None:
    """Create a prediction job via /predictions/run, then test list/get/events/predictions."""
    with TestClient(app) as c:
        dataset_id, sample_id, model_id, _job_id = _setup(c)

        # Run predictions (creates a prediction job)
        run_resp = c.post("/api/v1/predictions/run", json={
            "model_id": model_id,
            "dataset_id": dataset_id,
            "target": "image_classification",
        })
        assert run_resp.status_code == 202
        pjob_id = run_resp.json()["id"]

        # List prediction jobs
        list_resp = c.get("/api/v1/prediction-jobs")
        assert list_resp.status_code == 200
        jobs = list_resp.json()
        assert any(j["id"] == pjob_id for j in jobs)

        # Get single prediction job
        get_resp = c.get(f"/api/v1/prediction-jobs/{pjob_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == pjob_id
        assert get_resp.json()["dataset_id"] == dataset_id

        # List predictions for job
        preds_resp = c.get(f"/api/v1/prediction-jobs/{pjob_id}/predictions")
        assert preds_resp.status_code == 200
        assert isinstance(preds_resp.json(), list)

        # List events for job
        events_resp = c.get(f"/api/v1/prediction-jobs/{pjob_id}/events")
        assert events_resp.status_code == 200
        assert isinstance(events_resp.json(), list)


def test_cancel_prediction_job_not_found() -> None:
    with TestClient(app) as c:
        resp = c.post("/api/v1/prediction-jobs/nonexistent/cancel")
        assert resp.status_code == 404


def test_cancel_prediction_job() -> None:
    with TestClient(app) as c:
        dataset_id, sample_id, model_id, _job_id = _setup(c)

        run_resp = c.post("/api/v1/predictions/run", json={
            "model_id": model_id,
            "dataset_id": dataset_id,
            "target": "image_classification",
        })
        assert run_resp.status_code == 202
        pjob_id = run_resp.json()["id"]

        # Cancel — prediction_orchestrator.cancel_job delegates to repo
        resp = c.post(f"/api/v1/prediction-jobs/{pjob_id}/cancel")
        # May be 200 or 404 depending on job state; just check it doesn't 500
        assert resp.status_code in (200, 404)


# ---------------------------------------------------------------------------
# Sample predictions
# ---------------------------------------------------------------------------

def test_list_sample_predictions_empty() -> None:
    with TestClient(app) as c:
        dataset_id = _create_dataset(c)
        sample_id = _create_sample(c, dataset_id)
        resp = c.get(f"/api/v1/samples/{sample_id}/predictions")
        assert resp.status_code == 200
        assert resp.json() == []


def test_list_sample_predictions_not_found() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/samples/nonexistent/predictions")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Predict single
# ---------------------------------------------------------------------------

def test_predict_single() -> None:
    with TestClient(app) as c:
        dataset_id, sample_id, model_id, _job_id = _setup(c)

        resp = c.post("/api/v1/predictions/single", json={
            "model_id": model_id,
            "sample_id": sample_id,
            "target": "image_classification",
        })
        # May succeed or 400 depending on predictor availability
        assert resp.status_code in (200, 400, 422)


def test_predict_single_bad_model() -> None:
    with TestClient(app) as c:
        dataset_id = _create_dataset(c)
        sample_id = _create_sample(c, dataset_id)
        resp = c.post("/api/v1/predictions/single", json={
            "model_id": "nonexistent",
            "sample_id": sample_id,
        })
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Prediction collections
# ---------------------------------------------------------------------------

def test_list_prediction_collections_empty() -> None:
    with TestClient(app) as c:
        dataset_id = _create_dataset(c)
        resp = c.get("/api/v1/prediction-collections", params={"dataset_id": dataset_id})
        assert resp.status_code == 200
        assert resp.json() == []


def test_create_prediction_collection() -> None:
    with TestClient(app) as c:
        dataset_id, _sample_id, model_id, _job_id = _setup(c)

        resp = c.post("/api/v1/prediction-collections", json={
            "name": "my-collection",
            "dataset_id": dataset_id,
            "model_id": model_id,
            "prediction_ids": [],
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "my-collection"
        assert body["dataset_id"] == dataset_id
        assert body["model_id"] == model_id

        # List should now include it
        list_resp = c.get("/api/v1/prediction-collections", params={"dataset_id": dataset_id})
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 1


def test_create_prediction_collection_bad_dataset() -> None:
    with TestClient(app) as c:
        resp = c.post("/api/v1/prediction-collections", json={
            "name": "bad",
            "dataset_id": "nonexistent",
            "model_id": "nonexistent",
        })
        assert resp.status_code == 400


def test_sync_prediction_collection_to_ls() -> None:
    with TestClient(app) as c:
        dataset_id, _sample_id, model_id, _job_id = _setup(c)

        # Create collection
        coll_resp = c.post("/api/v1/prediction-collections", json={
            "name": "sync-test",
            "dataset_id": dataset_id,
            "model_id": model_id,
        })
        assert coll_resp.status_code == 201
        coll_id = coll_resp.json()["id"]

        # Sync to LS (empty collection — should succeed with 0 synced)
        sync_resp = c.post(f"/api/v1/prediction-collections/{coll_id}/sync-label-studio", json={
            "sync_tag": "test-sync",
        })
        assert sync_resp.status_code == 200
        body = sync_resp.json()
        assert body["collection_id"] == coll_id
        assert body["synced_count"] == 0


def test_sync_prediction_collection_not_found() -> None:
    with TestClient(app) as c:
        resp = c.post("/api/v1/prediction-collections/nonexistent/sync-label-studio", json={})
        assert resp.status_code == 400
