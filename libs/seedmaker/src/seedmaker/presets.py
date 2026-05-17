from __future__ import annotations

import sys
from typing import Any


from seedmaker import SeedConfig, SeedRunner


PRESETS = [
    {
        "name": "yolov8n-cls",
        "model_spec": {
            "framework": "pytorch",
            "base_model": "yolov8n-cls",
        },
        "omegaconf_yaml": """# YOLOv8 Nano Classification
model:
  name: yolov8n-cls
  pretrained: true

training:
  epochs: 100
  batch_size: 64
  imgsz: 224
  optimizer: AdamW
  lr0: 0.001
  weight_decay: 0.0005

augment:
  hsv_h: 0.015
  hsv_s: 0.7
  hsv_v: 0.4
  degrees: 0.0
  translate: 0.1
  scale: 0.5
  fliplr: 0.5
  mosaic: 0.0
""",
        "dataloader_ref": "ultralytics.data:build_classification_dataloader",
    },
    {
        "name": "yolov8s-cls",
        "model_spec": {
            "framework": "pytorch",
            "base_model": "yolov8s-cls",
        },
        "omegaconf_yaml": """# YOLOv8 Small Classification
model:
  name: yolov8s-cls
  pretrained: true

training:
  epochs: 100
  batch_size: 64
  imgsz: 224
  optimizer: AdamW
  lr0: 0.001
  weight_decay: 0.0005

augment:
  hsv_h: 0.015
  hsv_s: 0.7
  hsv_v: 0.4
  degrees: 0.0
  translate: 0.1
  scale: 0.5
  fliplr: 0.5
  mosaic: 0.0
""",
        "dataloader_ref": "ultralytics.data:build_classification_dataloader",
    },
    {
        "name": "resnet18",
        "model_spec": {
            "framework": "pytorch",
            "base_model": "resnet18",
        },
        "omegaconf_yaml": """# ResNet-18 Classification
model:
  name: resnet18
  pretrained: true

training:
  epochs: 50
  batch_size: 32
  learning_rate: 0.001
  optimizer: Adam
  weight_decay: 0.0001

scheduler:
  name: CosineAnnealingLR
  T_max: 50
""",
        "dataloader_ref": "torchvision.datasets:ImageFolder",
    },
    {
        "name": "resnet50",
        "model_spec": {
            "framework": "pytorch",
            "base_model": "resnet50",
        },
        "omegaconf_yaml": """# ResNet-50 Classification
model:
  name: resnet50
  pretrained: true

training:
  epochs: 50
  batch_size: 32
  learning_rate: 0.001
  optimizer: Adam
  weight_decay: 0.0001

scheduler:
  name: CosineAnnealingLR
  T_max: 50
""",
        "dataloader_ref": "torchvision.datasets:ImageFolder",
    },
]


def run_presets(args: Any) -> int:
    """Seed training presets into the platform.

    Uses SeedRunner for auth/setup, then creates presets via the API.
    """
    # Create a minimal config for SeedRunner auth/setup only
    config = SeedConfig(
        name="presets",
        dataset_name="__presets_only__",
        description="Seed training presets",
        defer_dataset=True,
    )
    runner = SeedRunner(
        config,
        api_url=getattr(args, "api_url", "http://localhost:8000"),
        no_promote=getattr(args, "no_promote", False),
    )
    runner.setup(skip_dataset=True)
    client = runner.client

    # Check existing presets
    print("Checking existing presets...")
    r = client.get("/api/v1/training-presets")
    existing_presets: set[str] = set()
    if r.status_code == 200:
        for p in r.json():
            existing_presets.add(p["name"])
        print(f"  Found {len(existing_presets)} existing presets: {existing_presets}")

    created = 0
    skipped = 0
    for preset in PRESETS:
        if preset["name"] in existing_presets:
            print(f"  Skipping '{preset['name']}' (already exists)")
            skipped += 1
            continue

        print(f"  Creating preset '{preset['name']}'...")
        r = client.post("/api/v1/training-presets", json=preset)
        if r.status_code == 200:
            print(f"    Created: {r.json()['id']}")
            created += 1
        else:
            print(f"    Failed: {r.status_code} {r.text}")

    print(f"\nDone! Created {created} presets, skipped {skipped}.")
    return 0


def main() -> int:
    """Standalone entry point for backward compatibility."""
    import argparse

    parser = argparse.ArgumentParser(description="Seed training presets")
    parser.add_argument(
        "--api-url", default="http://localhost:8000", help="Platform API base URL"
    )
    parser.add_argument(
        "--compose-file",
        default="infra/compose/docker-compose.yaml",
        help="Docker compose file path",
    )
    parser.add_argument(
        "--no-promote", action="store_true", help="Skip superadmin promotion"
    )
    parsed_args = parser.parse_args()
    return run_presets(parsed_args)


if __name__ == "__main__":
    sys.exit(main())
