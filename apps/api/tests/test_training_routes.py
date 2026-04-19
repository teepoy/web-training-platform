"""Route-level tests for training job endpoints.

Covers:
- POST /training-jobs/{job_id}/cancel
- POST /training-jobs/{job_id}/mark-left
- PATCH /training-jobs/{job_id}/public
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app, container
from tests.conftest import PRESET_ID

_TASK_SPEC = {"task_type": "classification", "label_space": ["cat", "dog"]}


def _create_dataset(c: TestClient) -> str:
    resp = c.post("/api/v1/datasets", json={
        "name": "train-route-ds",
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


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

def test_cancel_training_job() -> None:
    with TestClient(app) as c:
        dataset_id = _create_dataset(c)
        job_id = _create_job(c, dataset_id)
        resp = c.post(f"/api/v1/training-jobs/{job_id}/cancel")
        assert resp.status_code == 200
        body = resp.json()
        assert "cancelled" in body


def test_cancel_training_job_nonexistent() -> None:
    with TestClient(app) as c:
        resp = c.post("/api/v1/training-jobs/nonexistent/cancel")
        assert resp.status_code == 200
        # orchestrator.cancel_job returns False for missing jobs
        assert resp.json()["cancelled"] is False


# ---------------------------------------------------------------------------
# Mark user left
# ---------------------------------------------------------------------------

def test_mark_user_left() -> None:
    with TestClient(app) as c:
        dataset_id = _create_dataset(c)
        job_id = _create_job(c, dataset_id)
        resp = c.post(f"/api/v1/training-jobs/{job_id}/mark-left")
        assert resp.status_code == 200
        assert "marked" in resp.json()


def test_mark_user_left_not_found() -> None:
    with TestClient(app) as c:
        resp = c.post("/api/v1/training-jobs/nonexistent/mark-left")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Set public
# ---------------------------------------------------------------------------

def test_set_job_public() -> None:
    with TestClient(app) as c:
        dataset_id = _create_dataset(c)
        job_id = _create_job(c, dataset_id)

        # Set public
        resp = c.patch(f"/api/v1/training-jobs/{job_id}/public", json={"is_public": True})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Set private
        resp = c.patch(f"/api/v1/training-jobs/{job_id}/public", json={"is_public": False})
        assert resp.status_code == 200


def test_set_job_public_not_found() -> None:
    with TestClient(app) as c:
        resp = c.patch("/api/v1/training-jobs/nonexistent/public", json={"is_public": True})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Error handling: orchestrator failures become 502
# ---------------------------------------------------------------------------

def test_create_training_job_orchestrator_failure() -> None:
    """When orchestrator.start_job raises, the route returns 502."""
    with TestClient(app) as c:
        dataset_id = _create_dataset(c)
        with patch.object(
            container.orchestrator(), "start_job",
            new_callable=AsyncMock, side_effect=RuntimeError("Prefect unreachable"),
        ):
            resp = c.post("/api/v1/training-jobs", json={
                "dataset_id": dataset_id,
                "preset_id": PRESET_ID,
            })
        assert resp.status_code == 502
        assert "Prefect unreachable" in resp.json()["detail"]


def test_cancel_training_job_orchestrator_failure() -> None:
    """When orchestrator.cancel_job raises, the route returns 502."""
    with TestClient(app) as c:
        with patch.object(
            container.orchestrator(), "cancel_job",
            new_callable=AsyncMock, side_effect=RuntimeError("connection refused"),
        ):
            resp = c.post("/api/v1/training-jobs/some-id/cancel")
        assert resp.status_code == 502
