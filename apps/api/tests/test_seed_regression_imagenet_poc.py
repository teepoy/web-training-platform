from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers.factories import list_samples
from tests.helpers.fixtures import seeded_imagenet_poc  # noqa: F401


def test_seed_creates_imagenet_poc_dataset(seeded_imagenet_poc: tuple[str, str]) -> None:
    dataset_id, dataset_name = seeded_imagenet_poc
    assert dataset_id is not None
    assert dataset_name == "ImageNet-1K Real"


def test_imagenet_poc_samples_exist(seeded_imagenet_poc: tuple[str, str]) -> None:
    dataset_id, _dataset_name = seeded_imagenet_poc
    with TestClient(app) as client:
        result = list_samples(client, dataset_id)
    assert result["total"] >= 5
