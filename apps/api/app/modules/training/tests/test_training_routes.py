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
    get_training_submission,
)
from tests.conftest import DEFAULT_ORG_ID


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

def test_cancel_training_job_nonexistent() -> None:
    with TestClient(app) as c:
        resp = c.post("/api/v1/training-jobs/nonexistent/cancel")
        assert resp.status_code == 200
        # submission.cancel_job returns False for missing jobs
        assert resp.json()["cancelled"] is False


def test_cancel_training_job_is_scoped_to_current_org() -> None:
    with TestClient(app) as c:
        submission = app.state.app_context.training.training_submission
        with patch.object(
            submission,
            "cancel_job",
            new=AsyncMock(return_value=False),
        ) as cancel:
            app.dependency_overrides[get_training_submission] = lambda: submission
            try:
                resp = c.post("/api/v1/training-jobs/job-1/cancel")
            finally:
                app.dependency_overrides.pop(get_training_submission, None)

        assert resp.status_code == 200
        cancel.assert_awaited_once_with("job-1", org_id=DEFAULT_ORG_ID)


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
# Error handling: submission failures become 502
# ---------------------------------------------------------------------------

def test_cancel_training_job_submission_failure() -> None:
    """When submission.cancel_job raises, the route returns 502."""
    with TestClient(app) as c:
        submission = app.state.app_context.training.training_submission
        with patch.object(submission, "cancel_job", side_effect=RuntimeError("connection refused")):
            app.dependency_overrides[get_training_submission] = lambda: submission
            resp = c.post("/api/v1/training-jobs/some-id/cancel")
            app.dependency_overrides.pop(get_training_submission, None)
        assert resp.status_code == 502


def test_train_and_predict_defers_image_validation_to_runtime() -> None:
    """Submission validates labels; the runtime owns actual image filtering."""
    prefect_client = Mock()
    prefect_client.resolve_deployment_id = AsyncMock(return_value="deployment-1")
    prefect_client.create_flow_run_from_deployment = AsyncMock(
        return_value={"id": "flow-run-1"}
    )

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

        submission = app.state.app_context.training.training_submission
        with patch.object(submission, "_prefect_client", prefect_client):
            response = c.post(
                "/api/v1/training-jobs/train-and-predict",
                json={
                    "dataset_id": dataset_id,
                    "trainer_id": "yolo-sc-v1",
                },
            )

        assert response.status_code == 200
        dataset_revision_id = response.json()["train_job"]["dataset_revision_id"]
        assert dataset_revision_id

        jobs = c.get(
            "/api/v1/training-jobs",
            params={"dataset_id": dataset_id},
        )
        assert jobs.status_code == 200
        assert jobs.json()["total"] == 1
        assert jobs.json()["items"][0]["dataset_revision_id"] == dataset_revision_id

        current_revision = c.get(
            f"/api/v1/datasets/{dataset_id}/revisions/current"
        )
        assert current_revision.status_code == 200
        assert current_revision.json()["id"] == dataset_revision_id
        assert current_revision.json()["operation"] == "legacy_baseline"


def test_train_and_predict_submits_readable_seed_images() -> None:
    prefect_client = Mock()
    prefect_client.resolve_deployment_id = AsyncMock(return_value="deployment-1")
    prefect_client.create_flow_run_from_deployment = AsyncMock(
        return_value={"id": "flow-run-1"}
    )

    with TestClient(app) as c:
        submission = app.state.app_context.training.training_submission
        with patch.object(submission, "_prefect_client", prefect_client):
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
                    "trainer_id": "yolo-sc-v1",
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
    assert "missing_image_policy" not in parameters
    assert "output_contract" not in parameters
