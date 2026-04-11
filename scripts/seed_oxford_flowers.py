#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "datasets",
#     "pillow",
# ]
# ///
"""Seed the platform with the Oxford Flowers 102 dataset from HuggingFace.

Prerequisite: the platform API and Label Studio must be running
(e.g. via ``make up`` or ``make dev``).

Usage::

    # Against compose stack (promotes superadmin via docker exec)
    make seed

    # Manual (superadmin must already exist)
    uv run python scripts/seed_oxford_flowers.py --api-url http://localhost:8000

The script will:
1. Register a seed user (or reuse if already registered).
2. Promote the user to superadmin via ``docker compose exec`` (unless --no-promote).
3. Log in and create an organization + dataset with flower class labels.
4. Stream through all splits of Oxford Flowers 102 (~8k images) and POST each
   sample to the platform API, which in turn creates LS tasks (LS-first pattern).

Requires: ``pip install datasets Pillow httpx`` (or ``uv pip install ...``).
"""

from __future__ import annotations

import argparse
import base64
import io
import subprocess
import sys
import time

import httpx

SEED_EMAIL = "seed@example.com"
SEED_PASSWORD = "seed1234"
SEED_NAME = "Seed Admin"
ORG_NAME = "Flowers Lab"
ORG_SLUG = "flowers-lab"
DATASET_NAME = "Oxford Flowers 102"
COMPOSE_FILE = "infra/compose/docker-compose.yaml"


def _image_to_data_uri(img) -> str:
    """Convert a PIL Image to a JPEG data URI."""
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


def _api(client: httpx.Client, method: str, path: str, **kwargs) -> httpx.Response:
    resp = getattr(client, method)(path, **kwargs)
    return resp


def _wait_for_api_ready(client: httpx.Client, timeout_seconds: float = 120.0) -> None:
    """Wait until the API responds successfully to /health."""
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            resp = client.get("/health")
            if resp.status_code == 200:
                return
            last_error = f"unexpected status {resp.status_code}"
        except httpx.HTTPError as exc:
            last_error = str(exc)
        time.sleep(2.0)
    print(f"ERROR: API not ready after {timeout_seconds:.0f}s: {last_error}")
    sys.exit(1)


def _promote_superadmin(compose_file: str, email: str, password: str, name: str) -> None:
    """Promote user to superadmin via docker compose exec."""
    cmd = [
        "docker", "compose", "-f", compose_file,
        "exec", "-T", "api",
        "uv", "run", "python", "-m", "app.cli",
        "create-superadmin",
        f"--email={email}",
        f"--password={password}",
        f"--name={name}",
    ]
    print(f"  Promoting {email} to superadmin via docker exec ...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  WARNING: promote failed (rc={result.returncode}): {result.stderr.strip()}")
        print("  If running locally (not compose), use: make create-superadmin EMAIL=seed@example.com PASSWORD=seed1234 NAME='Seed Admin'")
    else:
        print(f"  {result.stdout.strip()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Oxford Flowers 102 dataset")
    parser.add_argument("--api-url", default="http://localhost:8000", help="Platform API base URL")
    parser.add_argument("--no-promote", action="store_true", help="Skip superadmin promotion (assume already done)")
    parser.add_argument("--compose-file", default=COMPOSE_FILE, help="Docker compose file path")
    parser.add_argument("--max-samples", type=int, default=0, help="Limit samples (0 = all)")
    parser.add_argument("--batch-report", type=int, default=100, help="Report progress every N samples")
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Step 0: Import HuggingFace datasets (fail fast if not installed)
    # ------------------------------------------------------------------
    try:
        from datasets import load_dataset  # type: ignore[import-untyped]
    except ImportError:
        print("ERROR: 'datasets' package not found. Install with: uv pip install datasets Pillow")
        sys.exit(1)

    api_url = args.api_url.rstrip("/")
    client = httpx.Client(base_url=api_url, timeout=30.0)

    print("[0/7] Waiting for API readiness ...")
    _wait_for_api_ready(client)
    print("  API is ready.")

    # ------------------------------------------------------------------
    # Step 1: Register user
    # ------------------------------------------------------------------
    print("[1/7] Registering seed user ...")
    resp = _api(client, "post", "/api/v1/auth/register", json={
        "email": SEED_EMAIL,
        "password": SEED_PASSWORD,
        "name": SEED_NAME,
    })
    if resp.status_code == 201:
        print(f"  Created user: {resp.json()['email']}")
    elif resp.status_code == 409:
        print("  User already exists, skipping.")
    else:
        print(f"  ERROR registering: {resp.status_code} {resp.text}")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Step 2: Promote to superadmin
    # ------------------------------------------------------------------
    print("[2/7] Promoting to superadmin ...")
    if args.no_promote:
        print("  Skipped (--no-promote).")
    else:
        _promote_superadmin(args.compose_file, SEED_EMAIL, SEED_PASSWORD, SEED_NAME)

    # ------------------------------------------------------------------
    # Step 3: Login
    # ------------------------------------------------------------------
    print("[3/7] Logging in ...")
    resp = _api(client, "post", "/api/v1/auth/login", json={
        "email": SEED_EMAIL,
        "password": SEED_PASSWORD,
    })
    if resp.status_code != 200:
        print(f"  ERROR login: {resp.status_code} {resp.text}")
        sys.exit(1)
    token = resp.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    print("  Logged in.")

    # ------------------------------------------------------------------
    # Step 4: Create organization
    # ------------------------------------------------------------------
    print("[4/7] Creating organization ...")
    resp = _api(client, "post", "/api/v1/organizations", json={
        "name": ORG_NAME,
        "slug": ORG_SLUG,
    })
    if resp.status_code == 201:
        org_id = resp.json()["id"]
        print(f"  Created org: {org_id}")
    elif resp.status_code == 409:
        # Already exists — fetch it
        resp = _api(client, "get", "/api/v1/organizations")
        orgs = resp.json()
        org_id = next((o["id"] for o in orgs if o["slug"] == ORG_SLUG), None)
        if org_id is None:
            print("  ERROR: org exists but could not find it in list")
            sys.exit(1)
        print(f"  Org already exists: {org_id}")
    else:
        print(f"  ERROR creating org: {resp.status_code} {resp.text}")
        sys.exit(1)

    client.headers["X-Organization-ID"] = org_id

    # ------------------------------------------------------------------
    # Step 5: Load HuggingFace dataset (before creating platform dataset,
    #         so we can extract label names from the HF features)
    # ------------------------------------------------------------------
    print("[5/7] Loading Oxford Flowers 102 from HuggingFace ...")
    hf_dataset = load_dataset("dpdl-benchmark/oxford_flowers102")

    # Extract label names from dataset features
    first_split = next(iter(hf_dataset.values()))
    label_names: list[str] = first_split.features["label"].names
    print(f"  {len(label_names)} classes, splits: {list(hf_dataset.keys())}")

    # ------------------------------------------------------------------
    # Step 6: Create dataset
    # ------------------------------------------------------------------
    print("[6/7] Creating dataset ...")
    resp = _api(client, "post", "/api/v1/datasets", json={
        "name": DATASET_NAME,
        "task_spec": {
            "task_type": "classification",
            "label_space": label_names,
        },
    })
    if resp.status_code == 200:
        dataset_id = resp.json()["id"]
        ls_project_id = resp.json().get("ls_project_id")
        print(f"  Created dataset: {dataset_id} (LS project: {ls_project_id})")
    else:
        print(f"  ERROR creating dataset: {resp.status_code} {resp.text}")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Step 7: Create samples from HuggingFace dataset
    # ------------------------------------------------------------------
    print("[7/7] Creating samples ...")

    total_created = 0
    total_skipped = 0
    batch_size = 5000
    batch: list[dict] = []
    t0 = time.time()
    max_samples = args.max_samples if args.max_samples > 0 else float("inf")

    for split_name in sorted(hf_dataset.keys()):
        split = hf_dataset[split_name]
        print(f"  Processing split '{split_name}' ({len(split)} samples) ...")

        for i, example in enumerate(split):
            if total_created >= max_samples:
                break

            image = example["image"]
            label_idx = example["label"]

            # Convert image to data URI
            data_uri = _image_to_data_uri(image)

            # Metadata includes the label index and flower name
            label_name = label_names[label_idx] if label_idx < len(label_names) else f"class_{label_idx}"
            metadata = {
                "split": split_name,
                "label_index": label_idx,
                "label_name": label_name,
                "hf_index": i,
            }

            batch.append({
                "image_uris": [data_uri],
                "metadata": metadata,
                "label": label_name,
            })

            if len(batch) >= batch_size or (args.max_samples > 0 and total_created + len(batch) >= max_samples):
                resp = _api(client, "post", f"/api/v1/datasets/{dataset_id}/samples/import", json={"items": batch})
                if resp.status_code == 200:
                    total_created += int(resp.json().get("imported", 0))
                else:
                    total_skipped += len(batch)
                    if total_skipped <= batch_size * 3:
                        print(f"    WARN batch ending at sample {i}: {resp.status_code} {resp.text[:120]}")
                batch = []

            if total_created % args.batch_report == 0 and total_created > 0:
                elapsed = time.time() - t0
                rate = total_created / elapsed if elapsed > 0 else 0
                print(f"    ... {total_created} samples created ({rate:.1f}/s)")

        if total_created >= max_samples:
            break

    elapsed = time.time() - t0
    print(f"\nDone! Created {total_created} samples, skipped {total_skipped} in {elapsed:.1f}s")
    print(f"Dataset ID: {dataset_id}")
    print(f"LS Project: {ls_project_id}")


if __name__ == "__main__":
    main()
