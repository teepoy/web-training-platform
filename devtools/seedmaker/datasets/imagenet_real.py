from __future__ import annotations

from seedmaker import FixtureConfig, IMAGENET_LABELS

config = FixtureConfig(
    name="imagenet-real",
    dataset_name="ImageNet-1K Real",
    description="ImageNet-1K dataset metadata used by API regression fixtures",
    label_space=IMAGENET_LABELS,
    dataset_type="image_classification",
    task_type="classification",
)
