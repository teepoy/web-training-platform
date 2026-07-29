"""Regression tests for the Wafer Demo seed fixture.

Verifies that ``seeded_wafer_demo`` produces a well-formed dataset with
spatial (wafer_x / wafer_y) metadata on at least 50 samples.
"""
from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers.factories import list_samples
from tests.helpers.fixtures import seeded_wafer_demo  # noqa: F401


@pytest.mark.regression
def test_seed_creates_wafer_dataset(seeded_wafer_demo: tuple[str, str]) -> None:  # noqa: F811
    """The fixture must expose a valid dataset_id and name 'Wafer Demo'."""
    dataset_id, dataset_name = seeded_wafer_demo
    assert dataset_id, "dataset_id must be truthy"
    assert dataset_name == "Wafer Demo", (
        f"Expected 'Wafer Demo', got {dataset_name!r}"
    )


@pytest.mark.regression
def test_wafer_samples_have_spatial_metadata(
    seeded_wafer_demo: tuple[str, str],  # noqa: F811
) -> None:
    """At least one wafer sample should carry wafer_x / wafer_y metadata."""
    dataset_id, _ = seeded_wafer_demo
    with TestClient(app) as client:
        resp = list_samples(client, dataset_id, limit=50)
    items = resp["items"]
    matched = any(
        "wafer_x" in item.get("metadata", {})
        and "wafer_y" in item.get("metadata", {})
        for item in items
    )
    assert matched, (
        f"No sample in dataset {dataset_id} has both wafer_x and wafer_y metadata"
    )


@pytest.mark.regression
def test_wafer_sample_count(seeded_wafer_demo: tuple[str, str]) -> None:  # noqa: F811
    """The fixture must produce at least 50 samples."""
    dataset_id, _ = seeded_wafer_demo
    with TestClient(app) as client:
        resp = list_samples(client, dataset_id, limit=100)
    total = resp["total"]
    assert total >= 50, (
        f"Expected >= 50 samples, got {total}"
    )


@pytest.mark.regression
def test_wafer_samples_have_readable_training_image_roles(
    seeded_wafer_demo: tuple[str, str],  # noqa: F811
) -> None:
    """Seeded SC samples carry real template and defective PNG payloads."""

    dataset_id, _ = seeded_wafer_demo
    with TestClient(app) as client:
        items = list_samples(client, dataset_id, limit=10)["items"]

    assert items
    for item in items:
        image_uris = item["image_uris"]
        assert len(image_uris) >= 2
        for uri in image_uris[:2]:
            assert uri.startswith("data:image/png;base64,")
            raw = base64.b64decode(uri.split(",", 1)[1], validate=True)
            with Image.open(io.BytesIO(raw)) as image:
                image.verify()

        shard_images = item["metadata"]["shard_images"]
        roles = {image["role"] for image in shard_images}
        assert {"patch_template", "patch_defective"} <= roles
