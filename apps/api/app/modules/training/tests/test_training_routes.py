"""Route-level tests for training job endpoints.

Covers:
- POST /training-jobs/{job_id}/cancel
- POST /training-jobs/{job_id}/mark-left
- PATCH /training-jobs/{job_id}/public
"""
from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.modules.sc.wafer_data_gen import build_patch_sample
from app.modules.training.port.http.deps import (
    get_training_orchestrator,
)


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

def test_cancel_training_job_nonexistent() -> None:
    with TestClient(app) as c:
        resp = c.post("/api/v1/training-jobs/nonexistent/cancel")
        assert resp.status_code == 200
        # orchestrator.cancel_job returns False for missing jobs
        assert resp.json()["cancelled"] is False


# ---------------------------------------------------------------------------
# Mark user left
# ---------------------------------------------------------------------------

def test_mark_user_left_not_found() -> None:
    with TestClient(app) as c:
        resp = c.post("/api/v1/training-jobs/nonexistent/mark-left")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Public visibility is disabled
# ---------------------------------------------------------------------------

def test_set_job_public_disabled() -> None:
    with TestClient(app) as c:
        resp = c.patch("/api/v1/training-jobs/nonexistent/public", json={"is_public": True})
        assert resp.status_code == 410
        assert resp.json()["detail"] == "Make Public is disabled"


# ---------------------------------------------------------------------------
# Error handling: orchestrator failures become 502
# ---------------------------------------------------------------------------

def test_cancel_training_job_orchestrator_failure() -> None:
    """When orchestrator.cancel_job raises, the route returns 502."""
    with TestClient(app) as c:
        orchestrator = app.state.app_context.training.training_orchestrator
        with patch.object(orchestrator, "cancel_job", side_effect=RuntimeError("connection refused")):
            app.dependency_overrides[get_training_orchestrator] = lambda: orchestrator
            resp = c.post("/api/v1/training-jobs/some-id/cancel")
            app.dependency_overrides.pop(get_training_orchestrator, None)
        assert resp.status_code == 502


def test_train_and_predict_rejects_unreadable_dataset_before_job_creation() -> None:
    """Readiness failures are returned before Prefect or GPU work is submitted."""

    with TestClient(app) as c:
        dataset_response = c.post(
            "/api/v1/datasets",
            json={
                "name": "unreadable-sc-training-dataset",
                "dataset_type": "image_sc",
                "task_spec": {
                    "task_type": "sc",
                    "label_space": ["Scratch", "Particle"],
                },
            },
        )
        assert dataset_response.status_code == 200
        dataset_id = dataset_response.json()["id"]

        for label in ("Scratch", "Particle"):
            sample_response = c.post(
                f"/api/v1/datasets/{dataset_id}/samples",
                json={"image_uris": [], "metadata": {}},
            )
            assert sample_response.status_code == 200
            annotation_response = c.post(
                "/api/v1/annotations",
                json={
                    "dataset_id": dataset_id,
                    "sample_id": sample_response.json()["id"],
                    "label": label,
                },
            )
            assert annotation_response.status_code == 200

        response = c.post(
            "/api/v1/training-jobs/train-and-predict",
            json={
                "dataset_id": dataset_id,
                "trainer_id": "resnet50-sc-v1",
            },
        )

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert detail["code"] == "dataset_training_readiness_failed"
        assert detail["annotated_samples"] == 2
        assert detail["readable_samples"] == 0
        assert detail["skipped_samples"] == 2
        assert detail["active_labels"] == []

        jobs = c.get(
            "/api/v1/training-jobs",
            params={"dataset_id": dataset_id},
        )
        assert jobs.status_code == 200
        assert jobs.json() == {"items": [], "total": 0}


def test_train_and_predict_submits_readable_seed_images() -> None:
    prefect_client = Mock()
    prefect_client.resolve_deployment_id = AsyncMock(return_value="deployment-1")
    prefect_client.create_flow_run_from_deployment = AsyncMock(
        return_value={"id": "flow-run-1"}
    )

    with TestClient(app) as c:
        orchestrator = app.state.app_context.training.training_orchestrator
        with patch.object(orchestrator, "_prefect_client", prefect_client):
            dataset_response = c.post(
                "/api/v1/datasets",
                json={
                    "name": "readable-sc-training-dataset",
                    "dataset_type": "image_sc",
                    "task_spec": {
                        "task_type": "sc",
                        "label_space": ["Scratch", "Particle"],
                    },
                },
            )
            assert dataset_response.status_code == 200
            dataset_id = dataset_response.json()["id"]

            for index, label in enumerate(("Scratch", "Particle")):
                patch_sample = build_patch_sample(index)
                sample_response = c.post(
                    f"/api/v1/datasets/{dataset_id}/samples",
                    json={
                        "image_uris": [
                            image.image_id
                            for image in patch_sample.shard_images
                        ],
                        "metadata": {
                            "sample_id": patch_sample.sample_id,
                            "inspection_time": patch_sample.inspection_time.isoformat()
                            if patch_sample.inspection_time
                            else "",
                            "wafer_key": patch_sample.wafer_key,
                            "defect_id": patch_sample.defect_id,
                            "shard_images": [
                                image.model_dump(mode="json")
                                for image in patch_sample.shard_images
                            ],
                        },
                    },
                )
                assert sample_response.status_code == 200
                annotation_response = c.post(
                    "/api/v1/annotations",
                    json={
                        "dataset_id": dataset_id,
                        "sample_id": sample_response.json()["id"],
                        "label": label,
                    },
                )
                assert annotation_response.status_code == 200

            response = c.post(
                "/api/v1/training-jobs/train-and-predict",
                json={
                    "dataset_id": dataset_id,
                    "trainer_id": "resnet50-sc-v1",
                },
            )

    assert response.status_code == 200
    assert response.json()["workflow_run_id"] == "flow-run-1"
    prefect_client.create_flow_run_from_deployment.assert_awaited_once()
    parameters = (
        prefect_client.create_flow_run_from_deployment.await_args.kwargs[
            "parameters"
        ]
    )
    assert parameters["dataset_id"] == dataset_id
    assert parameters["missing_image_policy"] == "skip"
