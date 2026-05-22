from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.helpers.factories import (
    create_test_training_job,
    list_samples,
    wait_for_job_completion,
)
from tests.helpers.fixtures import seeded_imagenet_mock  # noqa: F401


@pytest.mark.slow
def test_seed_creates_imagenet_mock_dataset(seeded_imagenet_mock: tuple[str, str]) -> None:  # noqa: F811
    dataset_id, dataset_name = seeded_imagenet_mock
    assert dataset_id is not None
    assert "ImageNet-1K Mock" == dataset_name


@pytest.mark.slow
def test_imagenet_mock_samples_exist(seeded_imagenet_mock: tuple[str, str]) -> None:  # noqa: F811
    dataset_id, dataset_name = seeded_imagenet_mock
    assert dataset_name == "ImageNet-1K Mock"
    with TestClient(app) as client:
        result = list_samples(client, dataset_id, limit=100)
        assert result["total"] >= 10, f"Expected >= 10 samples, got {result['total']}"


@pytest.mark.slow
def test_imagenet_mock_training_completes(seeded_imagenet_mock: tuple[str, str]) -> None:  # noqa: F811
    dataset_id, dataset_name = seeded_imagenet_mock
    assert dataset_name == "ImageNet-1K Mock"
    with TestClient(app) as client:
        job = create_test_training_job(client, dataset_id)
        finished = wait_for_job_completion(client, job["id"])
        assert finished["status"] == "completed", (
            f"Expected completed, got {finished['status']}"
        )
