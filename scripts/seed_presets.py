#!/usr/bin/env python3
"""Seed the platform with default training presets.

Usage::

    # Against compose stack
    uv run python scripts/seed_presets.py --compose-file infra/compose/docker-compose.yaml

    # Manual (superadmin must already exist)
    uv run python scripts/seed_presets.py --api-url http://localhost:8000 --no-promote
"""

from __future__ import annotations

import argparse
import sys

import httpx
from seed_common import (
    DEFAULT_COMPOSE_FILE,
    DEFAULT_ORG_NAME,
    DEFAULT_ORG_SLUG,
    DEFAULT_SEED_EMAIL,
    DEFAULT_SEED_NAME,
    DEFAULT_SEED_PASSWORD,
    login_seed_user,
    promote_superadmin,
    register_seed_user,
    resolve_or_create_org,
)

SEED_EMAIL = DEFAULT_SEED_EMAIL
SEED_PASSWORD = DEFAULT_SEED_PASSWORD
SEED_NAME = DEFAULT_SEED_NAME
ORG_NAME = DEFAULT_ORG_NAME
ORG_SLUG = DEFAULT_ORG_SLUG
COMPOSE_FILE = DEFAULT_COMPOSE_FILE

# Default presets to seed
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed training presets")
    parser.add_argument(
        "--api-url", default="http://localhost:8000", help="Platform API base URL"
    )
    parser.add_argument(
        "--compose-file", default=COMPOSE_FILE, help="Docker compose file path"
    )
    parser.add_argument(
        "--no-promote", action="store_true", help="Skip superadmin promotion"
    )
    args = parser.parse_args()

    api_url = args.api_url.rstrip("/")
    client = httpx.Client(base_url=api_url, timeout=30.0)

    # 1. Register user (ignore if already exists)
    print(f"Registering user {SEED_EMAIL}...")
    r = register_seed_user(client, SEED_EMAIL, SEED_PASSWORD, SEED_NAME)
    if r.status_code == 201:
        print("  User created.")
    elif r.status_code == 409:
        print("  User already exists.")
    else:
        print(f"  Warning: register returned {r.status_code}: {r.text}")

    # 2. Promote to superadmin via docker compose exec
    if not args.no_promote:
        print("Promoting user to superadmin...")
        promote_superadmin(args.compose_file, SEED_EMAIL, SEED_PASSWORD, SEED_NAME)

    # 3. Login
    print("Logging in...")
    r = login_seed_user(client, SEED_EMAIL, SEED_PASSWORD)
    if r.status_code != 200:
        print(f"Login failed: {r.status_code} {r.text}")
        return 1
    token = r.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    print("  Logged in.")

    # 4. Get or create organization
    print(f"Getting/creating organization '{ORG_NAME}'...")
    org_id = resolve_or_create_org(client, ORG_NAME, ORG_SLUG)
    if org_id:
        print(f"  Using org: {org_id}")
    else:
        print(
            "  Warning: could not resolve organization; continuing without X-Organization-ID"
        )

    if org_id:
        client.headers["X-Organization-ID"] = org_id

    # 5. Get existing presets
    print("Checking existing presets...")
    r = client.get("/api/v1/training-presets")
    existing_presets = set()
    if r.status_code == 200:
        for p in r.json():
            existing_presets.add(p["name"])
        print(f"  Found {len(existing_presets)} existing presets: {existing_presets}")

    # 6. Create presets
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


if __name__ == "__main__":
    sys.exit(main())
