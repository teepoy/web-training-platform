from __future__ import annotations

from seedmaker import FixtureConfig
from seedmaker.images import png_data_uri

LABELS = ["cluster-a", "cluster-b", "cluster-c"]

CLUSTER_OFFSETS = [(-7.5, 8.0), (10.0, -4.0), (2.0, 12.0)]

metadata_schema = {
    "scatter_x": {"type": "float", "description": "X coordinate for scatter plot."},
    "scatter_y": {"type": "float", "description": "Y coordinate for scatter plot."},
    "point_label": {"type": "string", "description": "Cluster/group label."},
    "sample_title": {"type": "string", "description": "Human-readable sample title."},
    "image_count": {"type": "integer", "description": "Number of images."},
    "primary_image_index": {
        "type": "integer",
        "description": "Default preview image index.",
    },
    "view_mode": {
        "type": "string",
        "description": "Marks dataset as multi-image scatter demo.",
    },
}

config = FixtureConfig(
    name="multi-image-scatter",
    dataset_name="Scatter Demo - Multi Image Samples",
    description="Multi-image samples with scatter coordinates for interactive demo. Configurable sample count and images per sample.",
    label_space=LABELS,
    metadata_schema=metadata_schema,
)


def _sample_images(
    sample_idx: int, label_idx: int, images_per_sample: int
) -> list[str]:
    base_hue = (label_idx * 83 + sample_idx * 17) % 255
    images: list[str] = []
    for image_idx in range(images_per_sample):
        red = (base_hue + image_idx * 19) % 255
        green = (80 + label_idx * 45 + image_idx * 27) % 255
        blue = (140 + sample_idx * 11 + image_idx * 31) % 255
        images.append(png_data_uri(96, red, green, blue))
    return images


def build_sample_item(idx: int, images_per_sample: int = 3) -> dict:
    """Build a single multi-image scatter sample item.

    Returns a dict with ``image_uris`` (``images_per_sample`` coloured PNGs),
    ``metadata`` (scatter_x, scatter_y, point_label, sample_title,
    image_count, primary_image_index, view_mode), and ``label``.
    """
    label_idx = idx % len(LABELS)
    label = LABELS[label_idx]
    offset_x, offset_y = CLUSTER_OFFSETS[label_idx]
    local_angle = idx / max(1, len(LABELS))
    scatter_x = round(offset_x + (idx % 5) * 1.75 + (local_angle * 0.15), 3)
    scatter_y = round(
        offset_y + ((idx // len(LABELS)) % 5) * 1.35 - (local_angle * 0.2), 3
    )
    image_uris = _sample_images(idx, label_idx, images_per_sample)
    return {
        "image_uris": image_uris,
        "metadata": {
            "scatter_x": scatter_x,
            "scatter_y": scatter_y,
            "point_label": label,
            "sample_title": f"{label} sample {idx + 1}",
            "image_count": len(image_uris),
            "primary_image_index": 0,
            "view_mode": "interactive-scatter-demo",
        },
        "label": label,
    }
