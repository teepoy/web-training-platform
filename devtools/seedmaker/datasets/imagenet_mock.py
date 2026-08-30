from __future__ import annotations

from seedmaker import FixtureConfig, IMAGENET_LABELS
from seedmaker.images import generate_synthetic_image

DATASET_NAME = "ImageNet-1K Mock"

config = FixtureConfig(
    name="imagenet-mock",
    dataset_name=DATASET_NAME,
    description="ImageNet-1K mock dataset with 1000 synthetic coloured-square samples",
    label_space=IMAGENET_LABELS,
    dataset_type="image_classification",
    task_type="classification",
)


def build_sample_item(idx: int) -> dict[str, object]:
    """Build one deterministic synthetic ImageNet test sample."""
    label = IMAGENET_LABELS[idx]
    return {
        "image_uris": [generate_synthetic_image(idx)],
        "metadata": {
            "source": "synthetic-test-fixture",
            "label_index": idx,
            "label_name": label,
        },
    }
