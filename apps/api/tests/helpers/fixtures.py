from __future__ import annotations

import base64
import io

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import TRAINER_ID
from tests.helpers.factories import (
    create_test_training_job,
    wait_for_job_completion,
)
from tests.helpers.test_seed_runner import TestSeedRunner

from seedmaker.labels import IMAGENET_LABELS

try:
    from seedmaker.labels import CIFAR100_LABELS
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
    Uses the seedmaker ``imagenet-mock`` recipe config and item builder.
    """
    from seedmaker.datasets.imagenet_mock import config, build_sample_item

    with TestClient(app) as client:
        runner = TestSeedRunner(client, config)
        runner.ensure_dataset()
        assert runner.dataset_id is not None
        runner.upload_samples(10, build_sample_item)
        job = create_test_training_job(client, runner.dataset_id, TRAINER_ID)
        wait_for_job_completion(client, job["id"])
        return (runner.dataset_id, config.dataset_name)


@pytest.fixture(scope="function")
def seeded_imagenet_poc() -> tuple[str, str]:
    """Seed an ImageNet-1K Real dataset with 5 synthetic samples.

    Creates the dataset, uploads 5 samples, launches a training job,
    waits for completion, and returns ``(dataset_id, dataset_name)``.
    Uses the seedmaker ``imagenet-real`` recipe config and the
    ``imagenet-mock`` item builder (real ImageNet images are too heavy
    for unit tests).
    """
    from seedmaker.datasets.imagenet_real import config
    from seedmaker.datasets.imagenet_mock import build_sample_item

    with TestClient(app) as client:
        runner = TestSeedRunner(client, config)
        runner.ensure_dataset()
        assert runner.dataset_id is not None
        runner.upload_samples(5, build_sample_item)
        job = create_test_training_job(client, runner.dataset_id, TRAINER_ID)
        wait_for_job_completion(client, job["id"])
        return (runner.dataset_id, config.dataset_name)


@pytest.fixture(scope="function")
def seeded_wafer_demo() -> tuple[str, str]:
    """Seed a Wafer Demo dataset with 50 samples carrying wafer coordinates.

    Uses the seedmaker ``wafer-demo`` recipe with SC PatchSample domain
    models.
    """
    from app.modules.sc.models import PatchSample
    from app.core.mapper_registry import mapper
    from app.shared.api.schemas import Sample
    from seedmaker.datasets.wafer_demo import config, build_patch_sample

    with TestClient(app) as client:
        runner = TestSeedRunner(client, config)
        runner.ensure_dataset()
        assert runner.dataset_id is not None

        did = runner.dataset_id
        to_sample_fn = mapper.get_mapper(PatchSample, Sample)

        def _build_item(idx: int) -> dict:
            ps = PatchSample(**build_patch_sample(idx).model_dump())
            sample = to_sample_fn(ps, dataset_id=did)
            return sample.model_dump(include={"image_uris", "metadata"})

        runner.upload_samples(50, _build_item)
        return (runner.dataset_id, config.dataset_name)


@pytest.fixture(scope="function")
def seeded_multi_image_scatter() -> tuple[str, str]:
    """Seed a Scatter Demo dataset with 6 multi-image samples (3 images each).

    Each sample carries ``scatter_x`` / ``scatter_y`` metadata for a
    3×2 grid.  Uses the seedmaker ``multi-image-scatter`` recipe config
    and item builder.
    """
    from seedmaker.datasets.multi_image_scatter import config, build_sample_item

    with TestClient(app) as client:
        runner = TestSeedRunner(client, config)
        runner.ensure_dataset()
        assert runner.dataset_id is not None
        runner.upload_samples(6, lambda idx: build_sample_item(idx, 3))
        return (runner.dataset_id, config.dataset_name)


@pytest.fixture(scope="function")
def seeded_mock_multi_image() -> tuple[str, str]:
    """Seed a Multi-Image Mock dataset with 10 samples (2 synthetic images each).

    Uses the seedmaker ``mock-multi-image`` recipe config for the
    dataset name and CIFAR-100 labels.  Samples use lightweight
    synthetic images so the fixture does not download CIFAR-100.
    """
    from seedmaker.datasets.mock_multi_image import config

    with TestClient(app) as client:
        runner = TestSeedRunner(client, config)
        runner.ensure_dataset()
        assert runner.dataset_id is not None

        uri = _synthetic_data_uri()
        for i in range(10):
            resp = client.post(
                f"/api/v1/datasets/{runner.dataset_id}/samples",
                json={"image_uris": [uri, uri], "metadata": {}},
            )
            assert resp.status_code == 200, (
                f"Failed multi-image sample {i}: {resp.status_code} {resp.text}"
            )
        return (runner.dataset_id, config.dataset_name)
