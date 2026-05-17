from __future__ import annotations

import random

from seedmaker import SeedConfig, SeedRunner, registry
from seedmaker.images import png_data_uri
from seedmaker.utils import api_request, _find_by_name

LABELS = ["wafer-point"]
RANDOM_SEED = 42
WAFER_RADIUS_NM = 150_000_000

metadata_schema = {
    "wafer_x": {"type": "float", "description": "Wafer X coordinate in nanometers."},
    "wafer_y": {"type": "float", "description": "Wafer Y coordinate in nanometers."},
    "wafer_index": {"type": "integer", "description": "Deterministic sample index."},
    "point_id": {"type": "string", "description": "Stable point identifier."},
    "seed": {"type": "integer", "description": "PRNG seed."},
}

config = SeedConfig(
    name="wafer-demo",
    dataset_name="Wafer Demo",
    description="Deterministic wafer-coordinate demo with configurable sample count. Supports --reset to recreate.",
    label_space=LABELS,
    metadata_schema=metadata_schema,
    defer_dataset=True,
)


def _wafer_coordinates(sample_idx: int) -> tuple[float, float]:
    rng = random.Random(RANDOM_SEED + sample_idx)
    radius_squared = WAFER_RADIUS_NM * WAFER_RADIUS_NM
    while True:
        x = float(rng.uniform(-WAFER_RADIUS_NM, WAFER_RADIUS_NM))
        y = float(rng.uniform(-WAFER_RADIUS_NM, WAFER_RADIUS_NM))
        if (x * x) + (y * y) <= radius_squared:
            return x, y


def run(args, runner: SeedRunner) -> int:
    samples: int = args.samples if args.samples is not None else 200_000
    batch_size: int = args.batch_size if args.batch_size is not None else 5000
    reset: bool = getattr(args, "reset", False)

    if samples < 1:
        print("ERROR: --samples must be >= 1")
        return 1
    if batch_size < 1:
        print("ERROR: --batch-size must be >= 1")
        return 1

    # Handle --reset
    if reset:
        r = api_request(runner.client, "get", "/api/v1/datasets")
        datasets = r.json() if r.status_code == 200 else []
        existing = _find_by_name(datasets, config.dataset_name)
        if existing is not None:
            r = api_request(
                runner.client, "delete", f"/api/v1/datasets/{existing['id']}"
            )
            if r.status_code != 204:
                print(f"  WARN: delete failed: {r.status_code} {r.text[:120]}")
            else:
                print(f"  Deleted existing dataset: {existing['id']}")
            runner._dataset_id = None

    runner.ensure_dataset()

    def build_sample_item(idx: int) -> dict:
        wx, wy = _wafer_coordinates(idx)
        return {
            "image_uris": [png_data_uri(16, 73, 109, 137)],
            "metadata": {
                "wafer_x": wx,
                "wafer_y": wy,
                "wafer_index": idx,
                "point_id": f"wafer-point-{idx + 1:06d}",
                "seed": RANDOM_SEED,
            },
        }

    runner.upload_samples(
        total=samples, item_builder=build_sample_item, batch_size=batch_size
    )
    runner.summary()
    return 0


registry.register(config, run)
