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
import subprocess
import sys

import httpx

SEED_EMAIL = "seed@example.com"
SEED_PASSWORD = "seed1234"
SEED_NAME = "Seed Admin"
ORG_NAME = "Default Org"
ORG_SLUG = "default-org"
COMPOSE_FILE = "infra/compose/docker-compose.yaml"

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
    parser.add_argument("--api-url", default="http://localhost:8000", help="Platform API base URL")
    parser.add_argument("--compose-file", default=COMPOSE_FILE, help="Docker compose file path")
    parser.add_argument("--no-promote", action="store_true", help="Skip superadmin promotion")
    args = parser.parse_args()

    api_url = args.api_url.rstrip("/")
    client = httpx.Client(base_url=api_url, timeout=30.0)

    # 1. Register user (ignore if already exists)
    print(f"Registering user {SEED_EMAIL}...")
    r = client.post("/api/v1/auth/register", json={
        "email": SEED_EMAIL,
        "password": SEED_PASSWORD,
        "name": SEED_NAME,
    })
    if r.status_code == 201:
        print("  User created.")
    elif r.status_code == 409:
        print("  User already exists.")
    else:
        print(f"  Warning: register returned {r.status_code}: {r.text}")

    # 2. Promote to superadmin via docker compose exec
    if not args.no_promote:
        print("Promoting user to superadmin...")
        try:
            subprocess.run(
                [
                    "docker", "compose", "-f", args.compose_file,
                    "exec", "-T", "api",
                    "uv", "run", "python", "-m", "app.cli", "create-superadmin",
                    f"--email={SEED_EMAIL}",
                    f"--password={SEED_PASSWORD}",
                    f"--name={SEED_NAME}",
                ],
                check=True,
                capture_output=True,
            )
            print("  Superadmin promotion complete.")
        except subprocess.CalledProcessError as e:
            print(f"  Warning: promotion failed: {e.stderr.decode()}")

    # 3. Login
    print("Logging in...")
    r = client.post("/api/v1/auth/login", json={
        "email": SEED_EMAIL,
        "password": SEED_PASSWORD,
    })
    if r.status_code != 200:
        print(f"Login failed: {r.status_code} {r.text}")
        return 1
    token = r.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    print("  Logged in.")

    # 4. Get or create organization
    print(f"Getting/creating organization '{ORG_NAME}'...")
    r = client.get("/api/v1/organizations")
    orgs = r.json() if r.status_code == 200 else []
    org_id = None
    for org in orgs:
        if org.get("slug") == ORG_SLUG or org.get("name") == ORG_NAME:
            org_id = org["id"]
            print(f"  Found existing org: {org_id}")
            break
    
    if not org_id:
        r = client.post("/api/v1/organizations", json={"name": ORG_NAME, "slug": ORG_SLUG})
        if r.status_code == 200:
            org_id = r.json()["id"]
            print(f"  Created org: {org_id}")
        else:
            print(f"  Warning: could not create org: {r.status_code} {r.text}")
            # Try to use the first available org
            if orgs:
                org_id = orgs[0]["id"]
                print(f"  Using first available org: {org_id}")

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
