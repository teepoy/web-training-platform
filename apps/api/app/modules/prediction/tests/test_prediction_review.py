from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.shared.api.schemas import Sample
from tests.conftest import create_dataset, create_sample, create_job, upload_model

def _setup_dataset_with_model(c: TestClient) -> tuple[str, str, str]:
    """Create dataset + job + model, return (dataset_id, model_id, job_id)."""
    dataset_id = create_dataset(c)
    job_id = create_job(c, dataset_id)
    model_id = upload_model(c, job_id)
    return dataset_id, model_id, job_id


# ---------------------------------------------------------------------------
# Test: Create review action with bad dataset → 400
# ---------------------------------------------------------------------------


def test_create_review_action_bad_dataset() -> None:
    with TestClient(app) as c:
        resp = c.post(
            "/api/v1/prediction-reviews",
            json={"dataset_id": "nonexistent", "model_id": "nonexistent"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Test: List review actions requires dataset_id query param
# ---------------------------------------------------------------------------


def test_list_review_actions_requires_dataset_id() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/prediction-reviews")
        assert resp.status_code == 422  # validation error


# ---------------------------------------------------------------------------
# Test: Get non-existent review action → 404
# ---------------------------------------------------------------------------


def test_get_review_action_not_found() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/prediction-reviews/nonexistent-id")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: Delete non-existent review action → 404
# ---------------------------------------------------------------------------


def test_delete_review_action_not_found() -> None:
    with TestClient(app) as c:
        resp = c.delete("/api/v1/prediction-reviews/nonexistent-id")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: Save review annotations for non-existent action → 400
# ---------------------------------------------------------------------------


def test_save_review_annotations_bad_action() -> None:
    with TestClient(app) as c:
        resp = c.post(
            "/api/v1/prediction-reviews/nonexistent-id/annotations",
            json={
                "items": [
                    {
                        "sample_id": "some-sample",
                        "predicted_label": "cat",
                        "final_label": "dog",
                        "confidence": None,
                        "prediction_id": None,
                    },
                ],
            },
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: List annotation versions for non-existent action → 404
# ---------------------------------------------------------------------------


def test_list_annotation_versions_not_found() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/prediction-reviews/nonexistent/annotation-versions")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: List export formats
# ---------------------------------------------------------------------------


def test_list_export_formats() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/export-formats")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        format_ids = {f["format_id"] for f in body}
        assert "annotation-version-full-context-v1" in format_ids
        assert "annotation-version-compact-v1" in format_ids


# ---------------------------------------------------------------------------
# Test: Preview export non-existent action → 404
# ---------------------------------------------------------------------------


def test_preview_export_not_found() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/prediction-reviews/nonexistent/export")
        assert resp.status_code == 404
