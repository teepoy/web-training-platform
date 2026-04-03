"""Seed the platform with Oxford Flowers 102 dataset from HuggingFace.

Usage:
    # From apps/api/ directory:
    uv run --extra dev --with datasets --with Pillow python scripts/seed_oxford_flowers.py

    # With custom API URL:
    API_BASE=http://localhost:9000/api/v1 uv run --extra dev --with datasets --with Pillow python scripts/seed_oxford_flowers.py

    # Limit samples (for quick testing):
    SEED_LIMIT=50 uv run --extra dev --with datasets --with Pillow python scripts/seed_oxford_flowers.py
"""

from __future__ import annotations

import io
import base64
import os
import sys
import time
from typing import Any

import httpx
from datasets import load_dataset

API_BASE = os.environ.get("API_BASE", "http://localhost:8000/api/v1")
SEED_LIMIT = int(os.environ.get("SEED_LIMIT", "0"))  # 0 = all
SPLIT = os.environ.get("SEED_SPLIT", "train")
DATASET_NAME = "Oxford Flowers 102"
HF_DATASET = "dpdl-benchmark/oxford_flowers102"
BATCH_ANNOTATION_DELAY = 0  # seconds between annotation batches (0 = no delay)


def post(client: httpx.Client, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    resp = client.post(f"{API_BASE}{path}", json=payload, timeout=30.0)
    if resp.status_code >= 400:
        print(f"  ERROR {resp.status_code}: {resp.text}", file=sys.stderr)
        resp.raise_for_status()
    return resp.json()


def get(client: httpx.Client, path: str) -> dict[str, Any]:
    resp = client.get(f"{API_BASE}{path}", timeout=30.0)
    return resp.json()


def image_to_data_uri(img: Any) -> str:
    """Convert a PIL Image to a JPEG data URI."""
    buf = io.BytesIO()
    img_rgb = img.convert("RGB") if img.mode != "RGB" else img
    img_rgb.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def main() -> None:
    print(f"Loading HuggingFace dataset: {HF_DATASET} (split={SPLIT})...")
    ds = load_dataset(HF_DATASET, split=SPLIT)
    label_names: list[str] = ds.features["label"].names  # type: ignore[union-attr]
    total = len(ds)

    if SEED_LIMIT > 0:
        total = min(SEED_LIMIT, total)
        print(f"  Limiting to {total} samples (SEED_LIMIT={SEED_LIMIT})")

    print(f"  {total} samples, {len(label_names)} classes")
    print(f"  Label examples: {label_names[:5]}...")
    print()

    client = httpx.Client()

    # 1. Create dataset
    print(f"Creating dataset '{DATASET_NAME}'...")
    dataset_resp = post(client, "/datasets", {
        "name": DATASET_NAME,
        "task_spec": {
            "task_type": "classification",
            "label_space": label_names,
        },
    })
    dataset_id = dataset_resp["id"]
    print(f"  Created dataset: {dataset_id}")
    print()

    # 2. Create samples + annotations
    print(f"Seeding {total} samples with annotations...")
    t0 = time.time()
    errors = 0

    for i in range(total):
        row = ds[i]
        label_idx = row["label"]
        label_str = label_names[label_idx]
        pil_image = row["image"]

        # Convert PIL image to data URI so the platform stores actual image data
        image_uri = image_to_data_uri(pil_image)

        # Create sample
        try:
            sample_resp = post(client, f"/datasets/{dataset_id}/samples", {
                "image_uris": [image_uri],
                "metadata": {
                    "hf_index": i,
                    "hf_split": SPLIT,
                    "label_index": label_idx,
                    "source": "oxford-flowers-102",
                },
            })
            sample_id = sample_resp["id"]
        except httpx.HTTPStatusError:
            errors += 1
            continue

        # Create annotation
        try:
            post(client, "/annotations", {
                "sample_id": sample_id,
                "label": label_str,
                "created_by": "seed-script",
            })
        except httpx.HTTPStatusError:
            errors += 1

        # Progress
        if (i + 1) % 50 == 0 or (i + 1) == total:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            print(f"  [{i + 1}/{total}] {rate:.1f} samples/s, {errors} errors")

    elapsed = time.time() - t0
    print()
    print(f"Done! Seeded {total - errors}/{total} samples in {elapsed:.1f}s")
    print(f"  Dataset ID: {dataset_id}")
    print(f"  Errors: {errors}")

    # 3. Verify
    print()
    print("Verifying...")
    ds_detail = get(client, f"/datasets/{dataset_id}")
    samples = get(client, f"/datasets/{dataset_id}/samples?limit=5&offset=0")
    print(f"  Dataset name: {ds_detail['name']}")
    print(f"  Label space: {len(ds_detail['task_spec']['label_space'])} classes")
    print(f"  Samples (first page): {samples['total']} total, showing {len(samples['items'])}")
    if samples["items"]:
        s = samples["items"][0]
        print(f"  First sample: id={s['id']}, uri_prefix={s['image_uris'][0][:40]}...")

    client.close()


if __name__ == "__main__":
    main()
