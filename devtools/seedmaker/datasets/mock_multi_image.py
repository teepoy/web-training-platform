from __future__ import annotations

from seedmaker import CIFAR100_LABELS, FixtureConfig

metadata_schema = {
    "scatter_x": {"type": "float", "description": "X coordinate for scatter plot."},
    "scatter_y": {"type": "float", "description": "Y coordinate for scatter plot."},
    "point_label": {"type": "string", "description": "Cluster/group label."},
    "sample_title": {"type": "string", "description": "Sample title."},
    "image_count": {"type": "integer", "description": "Number of images."},
    "primary_image_index": {
        "type": "integer",
        "description": "Default preview image index.",
    },
    "has_large_images": {
        "type": "boolean",
        "description": "Whether the sample has large optional images.",
    },
    "view_mode": {"type": "string", "description": "Fixture view mode."},
}

config = FixtureConfig(
    name="mock-multi-image",
    dataset_name="Multi-Image Mock (100K)",
    description="Multi-image dataset metadata used by API regression fixtures.",
    label_space=CIFAR100_LABELS,
    metadata_schema=metadata_schema,
)
