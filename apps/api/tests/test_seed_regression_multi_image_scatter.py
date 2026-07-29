from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.helpers.factories import list_samples
from tests.helpers.fixtures import seeded_multi_image_scatter  # noqa: F401


@pytest.mark.regression
def test_seed_creates_scatter_dataset(
    seeded_multi_image_scatter: tuple[str, str],  # noqa: F811
) -> None:
    dataset_id, name = seeded_multi_image_scatter
    assert dataset_id, "Expected a non-empty dataset_id"
    assert "Scatter" in name, f"Name should contain 'Scatter', got: {name}"


@pytest.mark.regression
def test_scatter_samples_have_multi_images_and_metadata(
    seeded_multi_image_scatter: tuple[str, str],  # noqa: F811
) -> None:
    dataset_id, _ = seeded_multi_image_scatter
    with TestClient(app) as client:
        result = list_samples(client, dataset_id)
    items: list[dict] = result["items"]
    assert result["total"] >= 1, "Expected at least 1 sample"

    multi_image_found = any(len(s.get("image_uris", [])) > 1 for s in items)
    assert multi_image_found, "Expected at least one sample with multiple image_uris"

    scatter_found = any(
        "scatter_x" in s.get("metadata", {}) and "scatter_y" in s.get("metadata", {})
        for s in items
    )
    assert scatter_found, "Expected at least one sample with scatter_x/scatter_y metadata"
