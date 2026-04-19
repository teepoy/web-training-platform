"""Tests for the worker-side training pipeline (run_training_pipeline).

These tests call ``run_training_pipeline`` directly as plain Python —
no Prefect server required.  They exercise the full code path that runs
inside a Prefect worker: DB access, preset loading, dynamic trainer
import, artifact persistence.
"""
from __future__ import annotations

import asyncio
import base64
import io

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.storage.minio_storage import InMemoryArtifactStorage
from tests.conftest import PRESET_ID


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x04\x00\x00\x00\x04\x08\x02"
    b"\x00\x00\x00&\x93\t)\x00\x00\x00\x14IDATx\x9cclpP`\x80\x01&\x06$\x80\x9b\x03"
    b"\x00-$\x00\xe8\xd2`\xe8\xf5\x00\x00\x00\x00IEND\xaeB`\x82"
)

_DATA_URI = "data:image/png;base64," + base64.b64encode(_TINY_PNG).decode()


def _seed_dataset_with_samples(
    client,
    n_samples: int = 3,
    labels: list[str] | None = None,
) -> tuple[str, list[str]]:
    """Create a dataset with labeled samples via the API.

    Returns ``(dataset_id, sample_ids)``.
    """
    labels = labels or ["cat", "dog"]
    ds = client.post(
        "/api/v1/datasets",
        json={
            "name": "runner-test-ds",
            "dataset_type": "image_classification",
            "task_spec": {"task_type": "classification", "label_space": labels},
        },
    )
    assert ds.status_code == 200
    dataset_id = ds.json()["id"]

    sample_ids: list[str] = []
    for i in range(n_samples):
        s = client.post(
            f"/api/v1/datasets/{dataset_id}/samples",
            json={"image_uris": [_DATA_URI]},
        )
        assert s.status_code == 200
        sid = s.json()["id"]
        sample_ids.append(sid)
        # Add an annotation so the trainer has labeled data
        label = labels[i % len(labels)]
        ann = client.post(
            "/api/v1/annotations",
            json={"sample_id": sid, "label": label, "source": "test"},
        )
        assert ann.status_code == 200

    return dataset_id, sample_ids


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_run_training_pipeline_completes() -> None:
    """Pipeline completes with real DB, preset, and in-memory storage."""
    with TestClient(app) as c:
        dataset_id, _ = _seed_dataset_with_samples(c, n_samples=4, labels=["cat", "dog"])

        from app.runtime.training_runner import run_training_pipeline

        storage = InMemoryArtifactStorage()
        result = asyncio.run(
            run_training_pipeline(
                job_id="test-train-001",
                dataset_id=dataset_id,
                preset_id=PRESET_ID,
                artifact_storage=storage,
            )
        )

        assert result["status"] == "completed"
        assert result["job_id"] == "test-train-001"
        artifacts = result.get("artifacts", [])
        assert len(artifacts) >= 1
        # At least one model artifact should have been persisted
        model_artifacts = [a for a in artifacts if a.get("kind") == "model"]
        assert len(model_artifacts) >= 1


def test_run_training_pipeline_missing_dataset() -> None:
    """Pipeline raises ValueError when dataset does not exist."""
    with TestClient(app):
        from app.runtime.training_runner import run_training_pipeline

        with pytest.raises(ValueError, match="Dataset not found"):
            asyncio.run(
                run_training_pipeline(
                    job_id="test-train-missing-ds",
                    dataset_id="nonexistent-dataset-id",
                    preset_id=PRESET_ID,
                    artifact_storage=InMemoryArtifactStorage(),
                )
            )


def test_run_training_pipeline_missing_preset() -> None:
    """Pipeline raises ValueError when preset does not exist."""
    with TestClient(app) as c:
        dataset_id, _ = _seed_dataset_with_samples(c, n_samples=1)

        from app.runtime.training_runner import run_training_pipeline

        with pytest.raises(ValueError, match="Preset not found"):
            asyncio.run(
                run_training_pipeline(
                    job_id="test-train-bad-preset",
                    dataset_id=dataset_id,
                    preset_id="nonexistent-preset-xyz",
                    artifact_storage=InMemoryArtifactStorage(),
                )
            )


def test_run_training_pipeline_empty_dataset() -> None:
    """Pipeline handles a dataset with zero samples gracefully.

    TorchTrainer should still complete by generating synthetic prototypes
    from the label space when no real labeled samples are available.
    """
    with TestClient(app) as c:
        ds = c.post(
            "/api/v1/datasets",
            json={
                "name": "empty-runner-ds",
                "dataset_type": "image_classification",
                "task_spec": {"task_type": "classification", "label_space": ["a", "b"]},
            },
        )
        assert ds.status_code == 200
        dataset_id = ds.json()["id"]

        from app.runtime.training_runner import run_training_pipeline

        storage = InMemoryArtifactStorage()
        result = asyncio.run(
            run_training_pipeline(
                job_id="test-train-empty",
                dataset_id=dataset_id,
                preset_id=PRESET_ID,
                artifact_storage=storage,
            )
        )

        assert result["status"] == "completed"


def test_run_training_pipeline_persists_artifacts_to_storage() -> None:
    """Model artifact is written to artifact storage."""
    with TestClient(app) as c:
        dataset_id, _ = _seed_dataset_with_samples(c, n_samples=2, labels=["x", "y"])

        from app.runtime.training_runner import run_training_pipeline

        storage = InMemoryArtifactStorage()
        result = asyncio.run(
            run_training_pipeline(
                job_id="test-train-artifacts",
                dataset_id=dataset_id,
                preset_id=PRESET_ID,
                artifact_storage=storage,
            )
        )

        model_uri = result["artifacts"][0]["uri"]
        assert model_uri
        # Verify the artifact was actually written to storage
        stored_bytes = asyncio.run(storage.get_bytes(model_uri))
        assert len(stored_bytes) > 0
