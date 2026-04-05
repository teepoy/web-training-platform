"""Load a HuggingFace dataset into the platform.

Downloads a HuggingFace image-classification dataset, creates the
corresponding dataset/samples/annotations on the platform API, and
optionally uploads the actual image bytes so the platform can serve
them directly.

Requirements:
    pip install httpx datasets Pillow

Usage:
    # Basic — loads Oxford Flowers 102 (default)
    python examples/load_hf_dataset.py

    # Quick test with 20 samples
    SEED_LIMIT=20 python examples/load_hf_dataset.py

    # Custom HuggingFace dataset
    HF_DATASET=beans DATASET_NAME="Bean Disease" python examples/load_hf_dataset.py

    # Different API URL
    API_BASE=http://localhost:9000/api/v1 python examples/load_hf_dataset.py

    # Upload actual image files (instead of inline data URIs)
    UPLOAD_IMAGES=1 python examples/load_hf_dataset.py

Environment variables:
    API_BASE        Platform API base URL (default: http://localhost:8000/api/v1)
    HF_DATASET      HuggingFace dataset name (default: dpdl-benchmark/oxford_flowers102)
    DATASET_NAME    Name for the platform dataset (default: derived from HF_DATASET)
    SEED_SPLIT      HF split to load (default: train)
    SEED_LIMIT      Max samples to load, 0 = all (default: 0)
    UPLOAD_IMAGES   Set to "1" to upload images via multipart upload endpoint
                    instead of embedding as data URIs (default: 0)
"""
from __future__ import annotations

import io
import base64
import os
import sys
import time
from pathlib import PurePosixPath
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE = os.environ.get("API_BASE", "http://localhost:8000/api/v1")
HF_DATASET = os.environ.get("HF_DATASET", "dpdl-benchmark/oxford_flowers102")
DATASET_NAME = os.environ.get("DATASET_NAME", "") or PurePosixPath(HF_DATASET).name.replace("_", " ").title()
SEED_SPLIT = os.environ.get("SEED_SPLIT", "train")
SEED_LIMIT = int(os.environ.get("SEED_LIMIT", "0"))
UPLOAD_IMAGES = os.environ.get("UPLOAD_IMAGES", "0") == "1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _post(client: httpx.Client, path: str, payload: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    resp = client.post(f"{API_BASE}{path}", json=payload, timeout=30.0, **kwargs)
    if resp.status_code >= 400:
        print(f"  ERROR {resp.status_code}: {resp.text}", file=sys.stderr)
        resp.raise_for_status()
    return resp.json()


def _get(client: httpx.Client, path: str) -> dict[str, Any]:
    resp = client.get(f"{API_BASE}{path}", timeout=30.0)
    return resp.json()


def _pil_to_data_uri(img: Any) -> str:
    """Convert a PIL Image to a JPEG data URI."""
    buf = io.BytesIO()
    rgb = img.convert("RGB") if img.mode != "RGB" else img
    rgb.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _pil_to_bytes(img: Any) -> bytes:
    """Convert a PIL Image to JPEG bytes."""
    buf = io.BytesIO()
    rgb = img.convert("RGB") if img.mode != "RGB" else img
    rgb.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # --- 1. Load HuggingFace dataset ---
    print(f"Loading HuggingFace dataset: {HF_DATASET} (split={SEED_SPLIT})...")
    from datasets import load_dataset

    ds = load_dataset(HF_DATASET, split=SEED_SPLIT)
    label_names: list[str] = ds.features["label"].names  # type: ignore[union-attr]
    total = len(ds)

    if SEED_LIMIT > 0:
        total = min(SEED_LIMIT, total)
        print(f"  Limiting to {total} samples (SEED_LIMIT={SEED_LIMIT})")

    print(f"  {total} samples, {len(label_names)} classes")
    print(f"  Upload mode: {'multipart file upload' if UPLOAD_IMAGES else 'inline data URIs'}")
    print()

    client = httpx.Client()

    # --- 2. Verify API is reachable ---
    try:
        health = client.get(f"{API_BASE.rsplit('/api', 1)[0]}/health", timeout=5.0)
        health.raise_for_status()
    except httpx.RequestError:
        print(f"ERROR: Cannot reach API at {API_BASE}", file=sys.stderr)
        print("  Start the API first:  make dev", file=sys.stderr)
        sys.exit(1)

    # --- 3. Create dataset ---
    print(f"Creating dataset '{DATASET_NAME}'...")
    dataset_resp = _post(client, "/datasets", {
        "name": DATASET_NAME,
        "task_spec": {
            "task_type": "classification",
            "label_space": label_names,
        },
    })
    dataset_id = dataset_resp["id"]
    print(f"  Created: {dataset_id}")
    print()

    # --- 4. Create samples + annotations ---
    print(f"Loading {total} samples...")
    t0 = time.time()
    errors = 0

    for i in range(total):
        row = ds[i]
        label_idx = row["label"]
        label_str = label_names[label_idx]
        pil_image = row["image"]

        # Create sample
        if UPLOAD_IMAGES:
            # Create sample with empty image_uris, then upload the file
            image_uris: list[str] = []
        else:
            # Embed image as data URI directly
            image_uris = [_pil_to_data_uri(pil_image)]

        try:
            sample_resp = _post(client, f"/datasets/{dataset_id}/samples", {
                "image_uris": image_uris,
                "metadata": {
                    "hf_index": i,
                    "hf_split": SEED_SPLIT,
                    "label_index": label_idx,
                    "source": HF_DATASET,
                },
            })
            sample_id = sample_resp["id"]
        except httpx.HTTPStatusError:
            errors += 1
            continue

        # Upload image file (multipart) if requested
        if UPLOAD_IMAGES:
            try:
                img_bytes = _pil_to_bytes(pil_image)
                resp = client.post(
                    f"{API_BASE}/samples/{sample_id}/upload",
                    files={"file": (f"image_{i}.jpg", img_bytes, "image/jpeg")},
                    timeout=30.0,
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError:
                errors += 1

        # Create annotation
        try:
            _post(client, "/annotations", {
                "sample_id": sample_id,
                "label": label_str,
                "created_by": "load-hf-script",
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
    print(f"Done! Loaded {total - errors}/{total} samples in {elapsed:.1f}s")
    if errors:
        print(f"  Errors: {errors}")

    # --- 5. Verify ---
    print()
    print("Verifying...")
    ds_detail = _get(client, f"/datasets/{dataset_id}")
    samples_page = _get(client, f"/datasets/{dataset_id}/samples?limit=5&offset=0")
    print(f"  Dataset:      {ds_detail['name']}")
    print(f"  ID:           {dataset_id}")
    print(f"  Label space:  {len(ds_detail['task_spec']['label_space'])} classes")
    print(f"  Samples:      {samples_page['total']} total")

    if samples_page["items"]:
        s = samples_page["items"][0]
        uri_preview = s["image_uris"][0][:60] + "..." if s["image_uris"] else "none"
        print(f"  First sample: id={s['id']}, uri={uri_preview}")

    # --- 6. Export hint ---
    print()
    print("To export this dataset as JSON:")
    print(f"  curl {API_BASE}/exports/{dataset_id} | python -m json.tool")
    print()
    print("To persist the export to storage:")
    print(f"  curl -X POST {API_BASE}/exports/{dataset_id}/persist")

    client.close()


if __name__ == "__main__":
    main()
