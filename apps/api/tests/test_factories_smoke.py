"""Rapid smoke test for the test helper factories.

Verifies the complete flow: dataset → samples → annotations → training job
→ wait_for_completion without error.
"""
from __future__ import annotations

import pytest

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers.factories import (
    create_test_annotations,
    create_test_dataset,
    create_test_samples,
    create_test_training_job,
    wait_for_job_completion,
)


@pytest.mark.slow
def test_factories_end_to_end_flow() -> None:
    """Exercise all core factories: dataset, samples, annotations, training job."""
    with TestClient(app) as client:
        ds = create_test_dataset(
            client,
            name="factory-test-ds",
            labels=["cat", "dog"],
        )
        dataset_id = ds["id"]
        assert ds["name"] == "factory-test-ds"
        assert ds["task_spec"]["label_space"] == ["cat", "dog"]

        samples = create_test_samples(client, dataset_id, count=3)
        assert len(samples) == 3
        sample_ids = [s["id"] for s in samples]
        assert all(s["dataset_id"] == dataset_id for s in samples)

        annotations = create_test_annotations(
            client, sample_ids, labels=["cat", "dog"]
        )
        assert len(annotations) == 3
        assert annotations[0]["label"] == "cat"
        assert annotations[1]["label"] == "dog"
        assert annotations[2]["label"] == "cat"

        job = create_test_training_job(client, dataset_id)
        assert job["status"] in ("running", "completed", "queued")
        job_id = job["id"]

        finished = wait_for_job_completion(client, job_id, timeout=60)
        assert finished["status"] == "completed", (
            f"Expected completed, got {finished['status']}"
        )
