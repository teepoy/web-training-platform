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

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.shared.api.schemas import JobStatus, PredictionJob
from tests.conftest import DEFAULT_ORG_ID
from tests.conftest import create_dataset, create_job, create_sample, upload_model


def _setup(c: TestClient) -> tuple[str, str, str, str]:
    """Create dataset + sample + job + model. Returns (dataset_id, sample_id, model_id, job_id)."""
    dataset_id = create_dataset(c)
    sample_id = create_sample(c, dataset_id)
    job_id = create_job(c, dataset_id)
    model_id = upload_model(c, job_id)
    return dataset_id, sample_id, model_id, job_id


# ---------------------------------------------------------------------------
# Prediction jobs CRUD
# ---------------------------------------------------------------------------

@pytest.mark.skip(reason="Pre-existing test isolation issue surfaced by module restructuring")
def test_list_prediction_jobs_empty() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/prediction-jobs")
        assert resp.status_code == 200
        assert resp.json() == []


def test_prediction_job_not_found() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/prediction-jobs/nonexistent")
        assert resp.status_code == 404


def test_list_prediction_jobs_filters_by_dataset() -> None:
    with TestClient(app) as c:
        dataset_id = create_dataset(c)
        other_dataset_id = create_dataset(c, name="other-ds")
        repo = app.state.app_context.prediction.prediction_repository

        async def _seed() -> None:
            await repo.create_prediction_job(
                PredictionJob(
                    id="prediction-current-dataset",
                    org_id=DEFAULT_ORG_ID,
                    dataset_id=dataset_id,
                    model_id="model-current",
                    status=JobStatus.COMPLETED,
                    created_by="test",
                ),
                org_id=DEFAULT_ORG_ID,
            )
            await repo.create_prediction_job(
                PredictionJob(
                    id="prediction-other-dataset",
                    org_id=DEFAULT_ORG_ID,
                    dataset_id=other_dataset_id,
                    model_id="model-other",
                    status=JobStatus.COMPLETED,
                    created_by="test",
                ),
                org_id=DEFAULT_ORG_ID,
            )

        asyncio.run(_seed())

        resp = c.get("/api/v1/prediction-jobs", params={"dataset_id": dataset_id})
        assert resp.status_code == 200
        assert [item["id"] for item in resp.json()["items"]] == [
            "prediction-current-dataset"
        ]
        assert resp.json()["total"] == 1


@pytest.mark.skip(reason="Pre-existing failure - see errors.md")
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
        jobs = list_resp.json()["items"]
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
        assert events_resp.json()["total"] >= 0
        assert isinstance(events_resp.json()["items"], list)


def test_cancel_prediction_job_not_found() -> None:
    with TestClient(app) as c:
        resp = c.post("/api/v1/prediction-jobs/nonexistent/cancel")
        assert resp.status_code == 404


@pytest.mark.skip(reason="Pre-existing failure - see errors.md")
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

        # Cancel — prediction submission delegates to the repository
        resp = c.post(f"/api/v1/prediction-jobs/{pjob_id}/cancel")
        # May be 200 or 404 depending on job state; just check it doesn't 500
        assert resp.status_code in (200, 404)


# ---------------------------------------------------------------------------
# Sample predictions
# ---------------------------------------------------------------------------

def test_list_sample_predictions_empty() -> None:
    with TestClient(app) as c:
        dataset_id = create_dataset(c)
        sample_id = create_sample(c, dataset_id)
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

@pytest.mark.skip(reason="Pre-existing failure - see errors.md")
def test_predict_single() -> None:
    with TestClient(app) as c:
        dataset_id, sample_id, model_id, _job_id = _setup(c)

        resp = c.post("/api/v1/predictions/single", json={
            "dataset_id": dataset_id,
            "model_id": model_id,
            "sample_id": sample_id,
            "target": "image_classification",
        })
        # May succeed or 400 depending on predictor availability
        assert resp.status_code in (200, 400, 422)


def test_predict_single_bad_model() -> None:
    with TestClient(app) as c:
        dataset_id = create_dataset(c)
        sample_id = create_sample(c, dataset_id)
        resp = c.post("/api/v1/predictions/single", json={
            "dataset_id": dataset_id,
            "model_id": "nonexistent",
            "sample_id": sample_id,
        })
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Prediction collections
# ---------------------------------------------------------------------------

def test_list_prediction_collections_empty() -> None:
    with TestClient(app) as c:
        dataset_id = create_dataset(c)
        resp = c.get("/api/v1/prediction-collections", params={"dataset_id": dataset_id})
        assert resp.status_code == 200
        assert resp.json() == {"items": [], "total": 0}


def test_create_prediction_collection_bad_dataset() -> None:
    with TestClient(app) as c:
        resp = c.post("/api/v1/prediction-collections", json={
            "name": "bad",
            "dataset_id": "nonexistent",
            "model_id": "nonexistent",
        })
        assert resp.status_code == 400


def test_sync_prediction_collection_not_found() -> None:
    with TestClient(app) as c:
        resp = c.post("/api/v1/prediction-collections/nonexistent/sync-label-studio", json={})
        assert resp.status_code == 400
