from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.helpers.factories import list_samples
from tests.helpers.fixtures import seeded_mock_multi_image  # noqa: F401


@pytest.mark.slow
def test_seed_creates_mock_multi_image_dataset(
    seeded_mock_multi_image: tuple[str, str],
) -> None:
    dataset_id, dataset_name = seeded_mock_multi_image
    assert dataset_id
    assert "Multi-Image" in dataset_name


@pytest.mark.slow
def test_mock_multi_image_samples_exist(
    seeded_mock_multi_image: tuple[str, str],
) -> None:
    dataset_id, _ = seeded_mock_multi_image
    with TestClient(app) as client:
        resp = list_samples(client, dataset_id)
        assert resp["total"] >= 10
