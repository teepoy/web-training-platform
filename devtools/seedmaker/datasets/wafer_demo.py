from __future__ import annotations

from seedmaker import FixtureConfig
from seedmaker.wafer_data import LABELS as WAFER_LABELS
from seedmaker.wafer_data import build_patch_sample

LABELS = list(WAFER_LABELS.values())

config = FixtureConfig(
    name="wafer-demo",
    dataset_name="Wafer Demo",
    dataset_type="image_sc",
    task_type="sc",
    description="Deterministic wafer-coordinate data used by API regression tests.",
    label_space=LABELS,
    metadata_schema={
        "sample_id": {"type": "string", "description": "Sample identifier."},
        "inspection_time": {
            "type": "string",
            "description": "ISO-8601 inspection timestamp.",
        },
        "wafer_key": {"type": "integer", "description": "Wafer key."},
        "defect_id": {"type": "string", "description": "Defect identifier."},
        "lot_id": {"type": "string", "description": "Lot identifier."},
        "wafer_x": {"type": "integer", "description": "Wafer X coordinate."},
        "wafer_y": {"type": "integer", "description": "Wafer Y coordinate."},
        "rough_bin": {"type": "integer", "description": "Rough bin."},
        "class_number": {"type": "integer", "description": "Class number."},
        "review_images": {"type": "json", "description": "Review images."},
        "shard_images": {"type": "json", "description": "Shard image refs."},
    },
)

__all__ = ["LABELS", "build_patch_sample", "config"]
