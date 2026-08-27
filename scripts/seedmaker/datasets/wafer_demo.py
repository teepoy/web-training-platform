from __future__ import annotations

import app.registrations  # noqa: F401  # trigger all mapper registrations

from app.core.mapper_registry import mapper
from app.modules.sc.models import PatchSample
from seedmaker.wafer_data import (
    LABELS as WAFER_LABELS,
    NUM_CLASSES,
    build_patch_sample,
)
from app.shared.api.schemas import Sample
from seedmaker import SeedConfig, SeedRunner, registry
from seedmaker.utils import _find_by_name, api_request

LABELS = list(WAFER_LABELS.values())
TOTAL_SAMPLES: int = 200_000

config = SeedConfig(
    name="wafer-demo",
    dataset_name="Wafer Demo",
    dataset_type="image_sc",
    task_type="sc",
    description=(
        "Deterministic wafer-coordinate demo with 100 classes and digit images. "
        "Always deletes and recreates if a dataset with the same name exists."
    ),
    label_space=LABELS,
    metadata_schema={
        "sample_id": {
            "type": "string",
            "description": "Unique sample/point identifier.",
        },
        "inspection_time": {
            "type": "string",
            "description": "ISO-8601 inspection timestamp.",
        },
        "wafer_key": {"type": "integer", "description": "Wafer key (lot index)."},
        "defect_id": {"type": "string", "description": "Defect identifier."},
        "lot_id": {"type": "string", "description": "Lot identifier."},
        "wafer_x": {"type": "integer", "description": "Wafer X coordinate (nm)."},
        "wafer_y": {"type": "integer", "description": "Wafer Y coordinate (nm)."},
        "rough_bin": {"type": "integer", "description": "Rough bin classification."},
        "class_number": {
            "type": "integer",
            "description": "Fine class number (digit in generated image).",
        },
        "review_images": {
            "type": "json",
            "description": "List of review image objects with image_url, image_name, image_id, image_type.",
        },
        "shard_images": {
            "type": "json",
            "description": "List of shard image refs with image_id, role, content_type.",
        },
    },
    defer_dataset=True,
)


def run(args, runner: SeedRunner) -> int:
    samples: int = args.samples if args.samples is not None else TOTAL_SAMPLES
    batch_size: int = args.batch_size if args.batch_size is not None else 5000

    if samples < 1:
        print("ERROR: --samples must be >= 1")
        return 1
    if batch_size < 1:
        print("ERROR: --batch-size must be >= 1")
        return 1

    # Always delete and recreate if a dataset with the same name exists
    r = api_request(runner.client, "get", "/api/v1/datasets")
    datasets = r.json() if r.status_code == 200 else []
    existing = _find_by_name(datasets, config.dataset_name)
    if existing is not None:
        r = api_request(runner.client, "delete", f"/api/v1/datasets/{existing['id']}")
        if r.status_code != 204:
            print(f"  WARN: delete failed: {r.status_code} {r.text[:120]}")
        else:
            print(f"  Deleted existing dataset: {existing['id']}")
        runner._dataset_id = None

    runner.ensure_dataset()

    dataset_id = runner.dataset_id
    assert dataset_id is not None, "ensure_dataset() must set dataset_id"

    to_sample_fn = mapper.get_mapper(PatchSample, Sample)

    def _build_item(idx: int) -> dict:
        ps = build_patch_sample(idx)
        sample = to_sample_fn(ps, dataset_id=dataset_id)
        return sample.model_dump(include={"image_uris", "metadata"})

    print(f"  Classes: {NUM_CLASSES}  |  Samples per class: ~{samples // NUM_CLASSES}")
    runner.upload_samples(
        total=samples, item_builder=_build_item, batch_size=batch_size
    )
    runner.summary()
    return 0


registry.register(config, run)
