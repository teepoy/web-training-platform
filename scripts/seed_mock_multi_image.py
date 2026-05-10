#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "httpx",
#     "Pillow",
#     "datasets",
#     "torch",
#     "torchvision",
# ]
# ///
"""Seed a 100K-sample multi-image mock dataset for stress-testing.

Creates a dataset where each sample has 3 required 32x32 CIFAR-100 images
and ~100 samples additionally have 4 optional 680x680 ImageNet-1K images.

Requires ``HF_TOKEN`` env var with an accepted HuggingFace license for
``ILSVRC/imagenet-1k``.

Usage::

    make seed-mock-multi-image
    make seed-mock-multi-image ARGS="--max-samples 1000 --large-samples 10"
"""

from __future__ import annotations

import argparse
import base64
import io
import math
import os
import random
import sys
import time

import httpx
from seed_common import (
    DEFAULT_COMPOSE_FILE,
    DEFAULT_ORG_NAME,
    DEFAULT_ORG_SLUG,
    DEFAULT_SEED_EMAIL,
    DEFAULT_SEED_NAME,
    DEFAULT_SEED_PASSWORD,
    api_request,
    login_seed_user,
    promote_superadmin,
    register_seed_user,
    resolve_or_create_org,
    wait_for_api_ready,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEED_EMAIL = DEFAULT_SEED_EMAIL
SEED_PASSWORD = DEFAULT_SEED_PASSWORD
SEED_NAME = DEFAULT_SEED_NAME
ORG_NAME = DEFAULT_ORG_NAME
ORG_SLUG = DEFAULT_ORG_SLUG
COMPOSE_FILE = DEFAULT_COMPOSE_FILE

DATASET_NAME = "Multi-Image Mock (100K)"
DATASET_TYPE = "image_classification"

DEFAULT_NUM_SAMPLES = 100_000
DEFAULT_LARGE_SAMPLES = 100
NUM_OPTIONAL_IMAGES = 4
REQUIRED_IMAGES_PER_SAMPLE = 3
BATCH_SIZE = 5_000
IMAGENET_POOL_SIZE = 400
IMAGENET_TARGET_SIZE = 680

# CIFAR-100 fine-grained labels (100 classes)
# Source: https://www.cs.toronto.edu/~kriz/cifar.html
CIFAR100_LABELS: list[str] = [
    "apple",
    "aquarium_fish",
    "baby",
    "bear",
    "beaver",
    "bed",
    "bee",
    "beetle",
    "bicycle",
    "bottle",
    "bowl",
    "boy",
    "bridge",
    "bus",
    "butterfly",
    "camel",
    "can",
    "castle",
    "caterpillar",
    "cattle",
    "chair",
    "chimpanzee",
    "clock",
    "cloud",
    "cockroach",
    "couch",
    "crab",
    "crocodile",
    "cup",
    "dinosaur",
    "dolphin",
    "elephant",
    "flatfish",
    "forest",
    "fox",
    "girl",
    "hamster",
    "house",
    "kangaroo",
    "keyboard",
    "lamp",
    "lawn_mower",
    "leopard",
    "lion",
    "lizard",
    "lobster",
    "man",
    "maple_tree",
    "motorcycle",
    "mountain",
    "mouse",
    "mushroom",
    "oak_tree",
    "orange",
    "orchid",
    "otter",
    "palm_tree",
    "pear",
    "pickup_truck",
    "pine_tree",
    "plain",
    "plate",
    "poppy",
    "porcupine",
    "possum",
    "rabbit",
    "raccoon",
    "ray",
    "road",
    "rocket",
    "rose",
    "sea",
    "seal",
    "shark",
    "shrew",
    "skunk",
    "skyscraper",
    "snail",
    "snake",
    "spider",
    "squirrel",
    "streetcar",
    "sunflower",
    "sweet_pepper",
    "table",
    "tank",
    "telephone",
    "television",
    "tiger",
    "tractor",
    "train",
    "trout",
    "tulip",
    "turtle",
    "wardrobe",
    "whale",
    "willow_tree",
    "wolf",
    "woman",
    "worm",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_by_name(items: list[dict], name: str) -> dict | None:
    for item in items:
        if item.get("name") == name:
            return item
    return None


def _scatter_center(label_idx: int) -> tuple[float, float]:
    """Return the cluster center for a given label index in a 10x10 grid."""
    cols = 10
    col = label_idx % cols
    row = label_idx // cols
    center_x = (col - 4.5) * 10.0
    center_y = (4.5 - row) * 10.0
    return center_x, center_y


def _scatter_coords(label_idx: int, sample_idx: int) -> tuple[float, float]:
    """Generate scatter plot coordinates with cluster-aligned jitter."""
    cx, cy = _scatter_center(label_idx)
    jitter_x = random.gauss(0, 1.5)
    jitter_y = random.gauss(0, 1.5)
    return round(cx + jitter_x, 3), round(cy + jitter_y, 3)


# ---------------------------------------------------------------------------
# Image pool builders
# ---------------------------------------------------------------------------


def _build_cifar100_pool() -> list[str]:
    """Download CIFAR-100 and return all 50K training images as PNG data URIs."""
    import torchvision  # type: ignore[import-untyped]

    print("  Downloading CIFAR-100 dataset via torchvision ...")
    t0 = time.time()
    train_set = torchvision.datasets.CIFAR100(
        root=os.path.expanduser("~/.cache/torchvision"),
        train=True,
        download=True,
    )
    print(f"  Downloaded {len(train_set)} images in {time.time() - t0:.1f}s")

    print("  Encoding CIFAR-100 images as PNG data URIs ...")
    t0 = time.time()
    pool: list[str] = []
    for idx in range(len(train_set)):
        img, _label = train_set[idx]
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        pool.append(f"data:image/png;base64,{b64}")
        if (idx + 1) % 10000 == 0:
            elapsed = time.time() - t0
            print(f"    ... {idx + 1}/{len(train_set)} images ({elapsed:.1f}s)")
    elapsed = time.time() - t0
    print(f"  Encoded {len(pool)} CIFAR-100 images in {elapsed:.1f}s")
    return pool


def _build_imagenet_pool(size: int) -> list[str]:
    """Stream ImageNet-1K validation images, resize, and return as JPEG data URIs."""
    from PIL import Image  # type: ignore[import-untyped]

    try:
        from datasets import load_dataset  # type: ignore[import-untyped]
    except ImportError:
        print(
            "  ERROR: 'datasets' package not found. Install: uv pip install datasets Pillow"
        )
        sys.exit(1)

    hf_token = os.environ.get("HF_TOKEN", "")
    if not hf_token:
        print("=" * 60)
        print("  ERROR: HF_TOKEN environment variable is not set.")
        print("  ImageNet-1K requires a HuggingFace access token with accepted license.")
        print("  1. Go to https://huggingface.co/settings/tokens")
        print("  2. Create a token with read access")
        print("  3. Visit https://huggingface.co/datasets/ILSVRC/imagenet-1k")
        print("     and accept the license terms")
        print("  4. Run: export HF_TOKEN=hf_your_token_here")
        print("=" * 60)
        sys.exit(1)

    print(f"  Streaming up to {size} ImageNet-1K validation images from HuggingFace ...")
    t0 = time.time()
    hf = load_dataset(
        "ILSVRC/imagenet-1k",
        split="validation",
        streaming=True,
        token=hf_token,
    )

    pool: list[str] = []
    for example in hf:
        if len(pool) >= size:
            break
        image = example["image"]
        if image.mode != "RGB":
            image = image.convert("RGB")
        resized = image.resize((IMAGENET_TARGET_SIZE, IMAGENET_TARGET_SIZE), Image.LANCZOS)
        buf = io.BytesIO()
        resized.save(buf, format="JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode()
        pool.append(f"data:image/jpeg;base64,{b64}")

        if len(pool) % 100 == 0 and len(pool) > 0:
            print(f"    ... {len(pool)}/{size} images ({time.time() - t0:.1f}s)")

    elapsed = time.time() - t0
    print(f"  Streamed {len(pool)} ImageNet images in {elapsed:.1f}s")
    return pool


# ---------------------------------------------------------------------------
# Sample builder
# ---------------------------------------------------------------------------


def _build_sample_item(
    sample_idx: int,
    cifar_pool: list[str],
    imagenet_pool: list[str],
    has_large_images: bool,
) -> dict:
    """Build a single sample item with required CIFAR-100 and optional ImageNet images."""
    label_idx = sample_idx % len(CIFAR100_LABELS)
    label = CIFAR100_LABELS[label_idx]

    # 3 required CIFAR-100 images (random picks from pool)
    required_uris = [random.choice(cifar_pool) for _ in range(REQUIRED_IMAGES_PER_SAMPLE)]

    # Optional ImageNet images
    optional_uris: list[str] = []
    if has_large_images and imagenet_pool:
        optional_uris = [random.choice(imagenet_pool) for _ in range(NUM_OPTIONAL_IMAGES)]

    image_uris = required_uris + optional_uris
    scatter_x, scatter_y = _scatter_coords(label_idx, sample_idx)

    metadata: dict = {
        "scatter_x": scatter_x,
        "scatter_y": scatter_y,
        "point_label": label,
        "sample_title": f"{label} sample {sample_idx + 1}",
        "image_count": len(image_uris),
        "primary_image_index": 0,
        "has_large_images": has_large_images,
        "view_mode": "multi-image-mock",
    }

    return {
        "image_uris": image_uris,
        "metadata": metadata,
        "label": label,
    }


# ---------------------------------------------------------------------------
# Dataset creation
# ---------------------------------------------------------------------------


def _create_dataset(client: httpx.Client) -> str:
    """Create or find the multi-image mock dataset."""
    metadata_schema = {
        "scatter_x": {
            "type": "float",
            "description": "X coordinate for plotting the sample in the interactive scatter component.",
        },
        "scatter_y": {
            "type": "float",
            "description": "Y coordinate for plotting the sample in the interactive scatter component.",
        },
        "point_label": {
            "type": "string",
            "description": "Cluster/group label for coloring or legend display.",
        },
        "sample_title": {
            "type": "string",
            "description": "Human-readable sample title for linked drill-down panels.",
        },
        "image_count": {
            "type": "integer",
            "description": "Number of images attached to the sample.",
        },
        "primary_image_index": {
            "type": "integer",
            "description": "Suggested default image index for preview surfaces.",
        },
        "has_large_images": {
            "type": "boolean",
            "description": "Whether this sample includes optional 680x680 ImageNet images.",
        },
        "view_mode": {
            "type": "string",
            "description": "Marks this dataset as a multi-image mock seed.",
        },
    }

    response = api_request(client, "get", "/api/v1/datasets")
    datasets = response.json() if response.status_code == 200 else []
    dataset = _find_by_name(datasets, DATASET_NAME)
    if dataset is not None:
        return str(dataset["id"])

    response = api_request(
        client,
        "post",
        "/api/v1/datasets",
        json={
            "name": DATASET_NAME,
            "dataset_type": DATASET_TYPE,
            "task_spec": {
                "task_type": "classification",
                "label_space": CIFAR100_LABELS,
                "metadata_schema": metadata_schema,
            },
        },
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"dataset creation failed: {response.status_code} {response.text}"
        )
    return str(response.json()["id"])


# ---------------------------------------------------------------------------
# Sample upload
# ---------------------------------------------------------------------------


def _upload_samples(
    client: httpx.Client,
    dataset_id: str,
    num_samples: int,
    num_large: int,
    cifar_pool: list[str],
    imagenet_pool: list[str],
) -> int:
    """Generate and upload samples in batches."""
    print(f"\n  Generating {num_samples} samples ...")
    print(f"    Large-image samples: {num_large} (each with {NUM_OPTIONAL_IMAGES} x 680x680 images)")
    print(f"    Batch size: {BATCH_SIZE}")

    # Determine which sample indices get large images (evenly spaced)
    large_indices: set[int] = set()
    if num_large > 0 and imagenet_pool:
        step = max(1, num_samples // num_large)
        for k in range(num_large):
            idx = min(k * step, num_samples - 1)
            large_indices.add(idx)
        print(f"    Large image indices: {len(large_indices)} entries (first: {min(large_indices)}, last: {max(large_indices)})")

    created = 0
    num_batches = math.ceil(num_samples / BATCH_SIZE)
    t0 = time.time()

    for batch_idx in range(num_batches):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, num_samples)
        batch: list[dict] = []

        for sample_idx in range(start, end):
            has_large = sample_idx in large_indices
            item = _build_sample_item(sample_idx, cifar_pool, imagenet_pool, has_large)
            batch.append(item)

        r = api_request(
            client,
            "post",
            f"/api/v1/datasets/{dataset_id}/samples/import",
            json={"items": batch},
        )
        if r.status_code == 200:
            imported = int(r.json().get("imported", 0))
            created += imported
        else:
            print(
                f"    WARN batch {batch_idx + 1}: {r.status_code} {r.text[:120]}"
            )

        elapsed = time.time() - t0
        rate = created / elapsed if elapsed > 0 else 0
        pct = 100 * (batch_idx + 1) / num_batches
        print(
            f"    [{batch_idx + 1}/{num_batches}] {created}/{num_samples} "
            f"samples ({pct:.0f}%) — {rate:.1f} samples/s"
        )

    elapsed = time.time() - t0
    print(f"\n  Uploaded {created} samples in {elapsed:.1f}s ({created / elapsed:.1f} samples/s)")
    return created


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed 100K-sample multi-image mock dataset for stress-testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--api-url", default="http://localhost:8000", help="Platform API base URL"
    )
    parser.add_argument(
        "--compose-file", default=COMPOSE_FILE, help="Docker compose file path"
    )
    parser.add_argument(
        "--no-promote", action="store_true", help="Skip superadmin promotion"
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=DEFAULT_NUM_SAMPLES,
        help=f"Total samples to create (default: {DEFAULT_NUM_SAMPLES})",
    )
    parser.add_argument(
        "--large-samples",
        type=int,
        default=DEFAULT_LARGE_SAMPLES,
        help=f"Samples that get optional 680x680 images (default: {DEFAULT_LARGE_SAMPLES})",
    )
    parser.add_argument(
        "--no-samples", action="store_true", help="Skip sample creation (dataset only)"
    )
    args = parser.parse_args()

    if args.large_samples > args.max_samples:
        print("ERROR: --large-samples cannot exceed --max-samples")
        return 1

    total_steps = 7
    print(f"\n{'=' * 50}")
    print(f"  Multi-Image Mock (100K) Seed Script")
    print(f"{'=' * 50}\n")

    api_url = args.api_url.rstrip("/")
    client = httpx.Client(base_url=api_url, timeout=60.0)

    # ------------------------------------------------------------------
    # Step 0: Wait for API readiness
    # ------------------------------------------------------------------
    print(f"[0/{total_steps}] Waiting for API readiness ...")
    try:
        wait_for_api_ready(client)
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1

    # ------------------------------------------------------------------
    # Step 1: Register seed user
    # ------------------------------------------------------------------
    print(f"[1/{total_steps}] Registering seed user ...")
    r = register_seed_user(client, SEED_EMAIL, SEED_PASSWORD, SEED_NAME)
    if r.status_code == 201:
        print(f"  Created user: {SEED_EMAIL}")
    elif r.status_code == 409:
        print("  User already exists, skipping.")
    else:
        print(f"  Warning: register returned {r.status_code}: {r.text}")

    # ------------------------------------------------------------------
    # Step 2: Promote to superadmin
    # ------------------------------------------------------------------
    print(f"\n[2/{total_steps}] Promoting to superadmin ...")
    if args.no_promote:
        print("  Skipped (--no-promote).")
    else:
        promote_superadmin(args.compose_file, SEED_EMAIL, SEED_PASSWORD, SEED_NAME)

    # ------------------------------------------------------------------
    # Step 3: Login
    # ------------------------------------------------------------------
    print(f"\n[3/{total_steps}] Logging in ...")
    r = login_seed_user(client, SEED_EMAIL, SEED_PASSWORD)
    if r.status_code != 200:
        print(f"  ERROR: login failed: {r.status_code} {r.text}")
        return 1
    token = r.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    print("  Logged in.")

    # ------------------------------------------------------------------
    # Step 4: Get or create organization
    # ------------------------------------------------------------------
    print(f"\n[4/{total_steps}] Getting/creating organization ...")
    org_id = resolve_or_create_org(client, ORG_NAME, ORG_SLUG)
    if org_id:
        print(f"  Using org: {org_id}")
        client.headers["X-Organization-ID"] = org_id
    else:
        print("  Warning: could not resolve organization; continuing without X-Organization-ID")

    # ------------------------------------------------------------------
    # Step 5: Create or find dataset
    # ------------------------------------------------------------------
    print(f"\n[5/{total_steps}] Creating/finding dataset '{DATASET_NAME}' ...")
    try:
        dataset_id = _create_dataset(client)
    except RuntimeError as exc:
        print(f"  ERROR: {exc}")
        return 1
    print(f"  Dataset ID: {dataset_id}")

    # ------------------------------------------------------------------
    # Step 6: Build image pools
    # ------------------------------------------------------------------
    print(f"\n[6/{total_steps}] Building image pools ...")

    print("  Building CIFAR-100 pool (32x32 required images) ...")
    try:
        cifar_pool = _build_cifar100_pool()
    except Exception as exc:
        print(f"  ERROR: Failed to build CIFAR-100 pool: {exc}")
        print("  Make sure torch and torchvision are installed: uv pip install torch torchvision")
        return 1
    print(f"  CIFAR-100 pool ready: {len(cifar_pool)} images")

    imagenet_pool: list[str] = []
    if args.large_samples > 0:
        print(f"\n  Building ImageNet pool ({IMAGENET_TARGET_SIZE}x{IMAGENET_TARGET_SIZE} optional images) ...")
        try:
            imagenet_pool = _build_imagenet_pool(IMAGENET_POOL_SIZE)
        except Exception as exc:
            print(f"  ERROR: Failed to build ImageNet pool: {exc}")
            return 1
        if not imagenet_pool:
            print("  WARNING: ImageNet pool is empty, proceeding with CIFAR-100 only images")
    else:
        print("  Skipping ImageNet pool (--large-samples=0)")

    # ------------------------------------------------------------------
    # Step 7: Create samples
    # ------------------------------------------------------------------
    sample_count = 0
    if args.no_samples:
        print("\n  Skipping sample creation (--no-samples).")
    else:
        print(f"\n[7/{total_steps}] Creating samples ...")

        r = api_request(
            client, "get", f"/api/v1/datasets/{dataset_id}/samples?offset=0&limit=1"
        )
        existing_total = r.json().get("total", 0) if r.status_code == 200 else 0
        if existing_total > 0:
            print(f"  Dataset already has {existing_total} samples, skipping.")
            sample_count = existing_total
        else:
            sample_count = _upload_samples(
                client,
                dataset_id,
                args.max_samples,
                args.large_samples,
                cifar_pool,
                imagenet_pool,
            )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print(f"\n{'=' * 50}")
    print(f"  Seed Summary")
    print(f"{'=' * 50}")
    print(f"  Dataset:    {DATASET_NAME}")
    print(f"  Dataset ID: {dataset_id}")
    print(f"  Labels:     {len(CIFAR100_LABELS)} CIFAR-100 classes")
    print(f"  Samples:    {sample_count}")
    print(f"  Required images/sample:  {REQUIRED_IMAGES_PER_SAMPLE} (32x32 CIFAR-100)")
    print(f"  Optional images/sample:  0 or {NUM_OPTIONAL_IMAGES} (680x680 ImageNet)")
    print(f"  Large-image samples:     {args.large_samples if sample_count > 0 else 0}")
    print(f"{'=' * 50}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
