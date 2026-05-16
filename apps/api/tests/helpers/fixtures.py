from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import PRESET_ID
from tests.helpers.factories import (
    create_test_dataset,
    create_test_samples,
    create_test_training_job,
    wait_for_job_completion,
)

# Ensure scripts/ is importable — both the repo root (for ``scripts.seed_maker.*``)
# and the ``scripts/`` directory (for ``seed_maker.*`` internal imports).
_REPO_ROOT = Path(__file__).resolve().parents[4]
for _p in (_REPO_ROOT, _REPO_ROOT / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from scripts.seed_maker.labels import IMAGENET_LABELS  # noqa: E402  # pyright: ignore[reportMissingImports]

try:
    from scripts.seed_maker.labels import CIFAR100_LABELS  # noqa: E402  # pyright: ignore[reportMissingImports]
except ImportError:
    CIFAR100_LABELS: list[str] = IMAGENET_LABELS[:100]


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------


def _synthetic_data_uri() -> str:
    """Tiny 1×1 gray PNG as a base64 data URI."""
    from PIL import Image

    img = Image.new("RGB", (1, 1), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"


# ---------------------------------------------------------------------------
# Seed fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def seeded_imagenet_mock() -> tuple[str, str]:
    """Seed an ImageNet-1K Mock dataset with 10 synthetic samples.

    Creates the dataset, uploads 10 samples, launches a training job,
    waits for completion, and returns ``(dataset_id, dataset_name)``.
    """
    with TestClient(app) as client:
        ds = create_test_dataset(client, "ImageNet-1K Mock", IMAGENET_LABELS)
        create_test_samples(client, ds["id"], 10)
        job = create_test_training_job(client, ds["id"], PRESET_ID)
        wait_for_job_completion(client, job["id"])
        return (ds["id"], ds["name"])


@pytest.fixture(scope="function")
def seeded_imagenet_poc() -> tuple[str, str]:
    """Seed an ImageNet-1K Real dataset with 5 synthetic samples.

    Creates the dataset, uploads 5 samples, launches a training job,
    waits for completion, and returns ``(dataset_id, dataset_name)``.
    """
    with TestClient(app) as client:
        ds = create_test_dataset(client, "ImageNet-1K Real", IMAGENET_LABELS)
        create_test_samples(client, ds["id"], 5)
        job = create_test_training_job(client, ds["id"], PRESET_ID)
        wait_for_job_completion(client, job["id"])
        return (ds["id"], ds["name"])


@pytest.fixture(scope="function")
def seeded_wafer_demo() -> tuple[str, str]:
    """Seed a Wafer Demo dataset with 50 samples carrying grid metadata.

    Each sample includes ``wafer_x`` / ``wafer_y`` spatial coordinates
    derived from its index (10×5 grid).  Uses direct ``client.post``
    because ``create_test_samples`` does not support custom metadata.
    """
    with TestClient(app) as client:
        ds = create_test_dataset(client, "Wafer Demo", ["defect"])
        uri = _synthetic_data_uri()
        for i in range(50):
            resp = client.post(
                f"/api/v1/datasets/{ds['id']}/samples",
                json={
                    "image_uris": [uri],
                    "metadata": {"wafer_x": i % 10, "wafer_y": i // 10},
                },
            )
            assert resp.status_code == 200, (
                f"Failed wafer sample {i}: {resp.status_code} {resp.text}"
            )
        return (ds["id"], ds["name"])


@pytest.fixture(scope="function")
def seeded_multi_image_scatter() -> tuple[str, str]:
    """Seed a Scatter Demo dataset with 6 multi-image samples (3 images each).

    Each sample carries ``scatter_x`` / ``scatter_y`` metadata for a
    3×2 grid.  Uses direct ``client.post`` for the multi-image format.
    """
    with TestClient(app) as client:
        ds = create_test_dataset(
            client,
            "Scatter Demo - Multi Image Samples",
            ["category_a", "category_b"],
        )
        uri = _synthetic_data_uri()
        for i in range(6):
            resp = client.post(
                f"/api/v1/datasets/{ds['id']}/samples",
                json={
                    "image_uris": [uri, uri, uri],
                    "metadata": {"scatter_x": i % 3, "scatter_y": i // 3},
                },
            )
            assert resp.status_code == 200, (
                f"Failed scatter sample {i}: {resp.status_code} {resp.text}"
            )
        return (ds["id"], ds["name"])


@pytest.fixture(scope="function")
def seeded_mock_multi_image() -> tuple[str, str]:
    """Seed a Multi-Image Mock dataset with 10 samples (2 images each).

    Uses CIFAR100_LABELS (100 labels) with a fallback to the first 100
    ImageNet labels if CIFAR-100 is unavailable.
    """
    with TestClient(app) as client:
        ds = create_test_dataset(
            client,
            "Multi-Image Mock (10)",
            CIFAR100_LABELS,
        )
        uri = _synthetic_data_uri()
        for i in range(10):
            resp = client.post(
                f"/api/v1/datasets/{ds['id']}/samples",
                json={"image_uris": [uri, uri], "metadata": {}},
            )
            assert resp.status_code == 200, (
                f"Failed multi-image sample {i}: {resp.status_code} {resp.text}"
            )
        return (ds["id"], ds["name"])
