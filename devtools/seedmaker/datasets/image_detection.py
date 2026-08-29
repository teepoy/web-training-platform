"""Object Detection Mock seed dataset.

Generates synthetic image detection samples with deterministic bounding boxes.
Each sample has one image (from picsum.photos) and one or more annotated boxes.

Usage::

    make seed ARGS="image-detection-mock"
    make seed ARGS="image-detection-mock --max-samples 200"
"""

from __future__ import annotations

from seedmaker import SeedConfig, SeedRunner, registry

DATASET_DISPLAY_NAME = "Object Detection Mock"
DATASET_DESCRIPTION = (
    "Synthetic object detection dataset. "
    "Each sample has one image with deterministic bounding boxes. "
    "Boxes are stored in sample metadata as normalized [0,1] coordinates."
)

LABEL_SPACE = ["car", "person", "bicycle", "truck", "bus"]

metadata_schema = {
    "width": {"type": "integer", "description": "Image width in pixels."},
    "height": {"type": "integer", "description": "Image height in pixels."},
    "boxes": {
        "type": "json",
        "description": "List of bounding boxes with label and normalized coords.",
    },
}

config = SeedConfig(
    name="image-detection-mock",
    dataset_name=DATASET_DISPLAY_NAME,
    description=DATASET_DESCRIPTION,
    dataset_type="image_detection",
    task_type="detection",
    label_space=LABEL_SPACE,
    metadata_schema=metadata_schema,
)


def _build_item(index: int) -> dict:
    """Build a single detection sample item.

    Boxes use deterministic but varied positions based on the index.
    All coordinates are normalized to [0, 1].
    """
    label = LABEL_SPACE[index % len(LABEL_SPACE)]
    x = (index * 13 % 60) / 100
    y = (index * 17 % 60) / 100
    # Some samples get a second box for variety
    boxes = [{"label": label, "x": x, "y": y, "width": 0.25, "height": 0.2}]
    if index % 5 == 0:
        label2 = LABEL_SPACE[(index + 2) % len(LABEL_SPACE)]
        x2 = (index * 29 % 60) / 100 + 0.3
        y2 = (index * 31 % 60) / 100 + 0.3
        boxes.append({"label": label2, "x": x2, "y": y2, "width": 0.2, "height": 0.15})
    return {
        "image_uris": [f"https://picsum.photos/seed/det{index}/640/480"],
        "metadata": {
            "width": 640,
            "height": 480,
            "boxes": boxes,
        },
    }


def run(args, runner: SeedRunner) -> int:
    max_samples: int = args.max_samples if args.max_samples is not None else 500

    runner.upload_samples(
        total=max_samples,
        item_builder=_build_item,
    )
    return 0


registry.register(config, run)
