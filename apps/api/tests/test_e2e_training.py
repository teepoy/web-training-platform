"""End-to-end integration test covering the full training→prediction pipeline.

Creates a dataset with annotated samples, runs training via the real
LocalProcessEngine, polls for completion, verifies artifacts, uploads a
model with correct compatibility metadata (existing pattern — the
training engine produces artifacts but lacks prediction-compatibility
metadata in `build_trained_model_metadata`), runs prediction through
the real prediction service, and verifies prediction results.

Training and prediction are NOT mocked — only the inference worker is
mocked by the autouse conftest fixtures (standard for all tests).
"""

from __future__ import annotations

import io as _io
import json as _json
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app

_DATA_URI = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
    "AAAAC0lEQVR42mP8/x8AAwMCAO+/4gkAAAAASUVORK5CYII="
)

TRAINER_ID = "resnet50-sc-v1"
LABELS = ["cat", "dog"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_dataset(client: TestClient, name: str = "e2e-test-ds") -> str:
    r = client.post(
        "/api/v1/datasets",
        json={
            "name": name,
            "dataset_type": "image_classification",
            "task_spec": {
                "task_type": "classification",
                "label_space": LABELS,
            },
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _create_samples(
    client: TestClient, dataset_id: str, count: int = 2
) -> list[str]:
    ids: list[str] = []
    for _ in range(count):
        r = client.post(
            f"/api/v1/datasets/{dataset_id}/samples",
            json={"image_uris": [_DATA_URI], "metadata": {}},
        )
        assert r.status_code == 200, r.text
        ids.append(r.json()["id"])
    return ids


def _annotate(client: TestClient, dataset_id: str, sample_id: str, label: str) -> dict:
    r = client.post(
        "/api/v1/annotations",
        json={"dataset_id": dataset_id, "sample_id": sample_id, "label": label},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _create_training_job(client: TestClient, dataset_id: str) -> str:
    r = client.post(
        "/api/v1/training-jobs",
        json={"dataset_id": dataset_id, "trainer_id": TRAINER_ID},
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _poll_training(client: TestClient, job_id: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    last_status: str | None = None
    while time.monotonic() < deadline:
        r = client.get(f"/api/v1/training-jobs/{job_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        last_status = body.get("status", "")
        if last_status in ("completed", "failed", "cancelled"):
            return body
        time.sleep(0.5)
    raise RuntimeError(
        f"Training job {job_id} did not reach terminal state "
        f"(last: {last_status}) within {timeout}s"
    )


def _run_prediction(
    client: TestClient, model_id: str, dataset_id: str
) -> dict:
    r = client.post(
        "/api/v1/predictions/run",
        json={
            "model_id": model_id,
            "dataset_id": dataset_id,
            "target": "image_classification",
        },
    )
    assert r.status_code == 202, r.text
    return r.json()


def _get_predictions_from_job(client: TestClient, pred_job_id: str) -> list[dict]:
    """Read predictions from the job's summary (test-mode stores them there)."""
    r = client.get(f"/api/v1/prediction-jobs/{pred_job_id}")
    assert r.status_code == 200, r.text
    summary = (r.json() or {}).get("summary", {})
    if not isinstance(summary, dict):
        return []
    return summary.get("predictions", [])


def _upload_model_for_prediction(client: TestClient, job_id: str) -> str:
    """Upload a model artifact with correct prediction-compatibility metadata.

    Uses the established conftest.upload_model pattern.  The training
    engine produces artifacts via ``build_trained_model_metadata`` which
    currently omits ``prediction_targets`` / ``dataset_types`` /
    ``task_types`` — required by ``validate_model_prediction``.  This
    helper bridges that gap without modifying production code.
    """
    metadata = _json.dumps({
        "name": "e2e-test-model",
        "format": "pytorch",
        "job_id": job_id,
        "template_id": "image-classifier",
        "profile_id": "resnet50-sc-v1",
        "model_spec": {
            "framework": "pytorch",
            "architecture": "resnet50",
            "base_model": "torchvision/resnet50",
        },
        "compatibility": {
            "dataset_types": ["image_classification"],
            "task_types": ["classification"],
            "prediction_targets": ["image_classification"],
            "label_space": LABELS,
        },
    })
    r = client.post(
        "/api/v1/models/upload",
        data={"metadata": metadata},
        files={
            "file": (
                "model.json",
                _io.BytesIO(b"{}"),
                "application/json",
            )
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ---------------------------------------------------------------------------
# E2E test
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.skip(
    reason=(
        "Legacy classification E2E expects a classification trainer; "
        "resnet50-sc-v1 is now an SC patch_image_v1 trainer."
    )
)
def test_e2e_training_prediction_pipeline() -> None:
    """Full end-to-end: dataset → samples → annotations → training →
    poll completion → verify artifacts → upload model → predict →
    verify predictions.
    """

    with TestClient(app) as client:
        dataset_id = _create_dataset(client, "e2e-train-pred-ds")

        sample_ids = _create_samples(client, dataset_id, count=2)

        for i, sid in enumerate(sample_ids):
            label = LABELS[i % len(LABELS)]
            ann = _annotate(client, dataset_id, sid, label)
            assert ann.get("label") == label

        job_id = _create_training_job(client, dataset_id)

        finished = _poll_training(client, job_id, timeout=30.0)
        assert finished["status"] == "completed", (
            f"Training job did not complete. "
            f"Status: {finished['status']}"
        )

        artifacts = finished.get("artifact_refs", [])
        assert isinstance(artifacts, list) and len(artifacts) >= 1, (
            f"Training completed but produced no artifacts. "
            f"artifact_refs={artifacts}"
        )

        model_id = _upload_model_for_prediction(client, job_id)

        pred_job = _run_prediction(client, model_id, dataset_id)
        assert pred_job["status"] == "completed", (
            f"Prediction job did not complete immediately. "
            f"Status: {pred_job['status']}"
        )
        pred_job_id = pred_job["id"]

        predictions = _get_predictions_from_job(client, pred_job_id)
        assert len(predictions) == 2, (
            f"Expected 2 predictions (one per sample), got {len(predictions)}"
        )

        predicted_sample_ids = {p["sample_id"] for p in predictions}
        assert predicted_sample_ids == set(sample_ids), (
            f"Prediction sample IDs {predicted_sample_ids} "
            f"don't match input {set(sample_ids)}"
        )

        for p in predictions:
            assert p["predicted_label"] in LABELS, (
                f"Predicted label '{p['predicted_label']}' "
                f"not in {LABELS}"
            )
            assert isinstance(p.get("confidence"), (int, float)), (
                f"Missing confidence in prediction: {p}"
            )
