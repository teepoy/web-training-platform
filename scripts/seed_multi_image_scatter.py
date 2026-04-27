#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "httpx",
# ]
# ///
"""Seed a small multi-image dataset for scatter-viewer demos.

Usage::

    make seed-multi-image-scatter
    make seed-multi-image-scatter ARGS="--samples 24 --images-per-sample 4"

Creates a dataset where each sample contains multiple synthetic images plus
explicit scatter coordinates in metadata so the interactive scatter component
can link each point back to a rich sample viewer.
"""

from __future__ import annotations

import argparse
import base64
import random
import struct
import sys
import zlib

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

SEED_EMAIL = DEFAULT_SEED_EMAIL
SEED_PASSWORD = DEFAULT_SEED_PASSWORD
SEED_NAME = DEFAULT_SEED_NAME
ORG_NAME = DEFAULT_ORG_NAME
ORG_SLUG = DEFAULT_ORG_SLUG
COMPOSE_FILE = DEFAULT_COMPOSE_FILE

DATASET_NAME = "Scatter Demo - Multi Image Samples"
LABELS = ["cluster-a", "cluster-b", "cluster-c"]


def _find_by_name(items: list[dict], name: str) -> dict | None:
    for item in items:
        if item.get("name") == name:
            return item
    return None


def _png_data_uri(size: int, red: int, green: int, blue: int) -> str:
    raw_rows = bytearray()
    for _y in range(size):
        raw_rows.append(0)
        for _x in range(size):
            raw_rows.extend((red, green, blue))

    def _chunk(tag: bytes, data: bytes) -> bytes:
        payload = tag + data
        return (
            struct.pack(">I", len(data))
            + payload
            + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
        )

    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
    png += _chunk(b"IDAT", zlib.compress(bytes(raw_rows), 6))
    png += _chunk(b"IEND", b"")
    return f"data:image/png;base64,{base64.b64encode(png).decode()}"


def _sample_images(
    sample_idx: int, label_idx: int, images_per_sample: int
) -> list[str]:
    base_hue = (label_idx * 83 + sample_idx * 17) % 255
    images: list[str] = []
    for image_idx in range(images_per_sample):
        red = (base_hue + image_idx * 19) % 255
        green = (80 + label_idx * 45 + image_idx * 27) % 255
        blue = (140 + sample_idx * 11 + image_idx * 31) % 255
        images.append(_png_data_uri(96, red, green, blue))
    return images


def _build_sample_item(sample_idx: int, images_per_sample: int) -> dict:
    label_idx = sample_idx % len(LABELS)
    label = LABELS[label_idx]
    cluster_offsets = [(-7.5, 8.0), (10.0, -4.0), (2.0, 12.0)]
    offset_x, offset_y = cluster_offsets[label_idx]
    local_angle = sample_idx / max(1, len(LABELS))
    scatter_x = round(offset_x + (sample_idx % 5) * 1.75 + (local_angle * 0.15), 3)
    scatter_y = round(
        offset_y + ((sample_idx // len(LABELS)) % 5) * 1.35 - (local_angle * 0.2), 3
    )
    image_uris = _sample_images(sample_idx, label_idx, images_per_sample)
    metadata = {
        "scatter_x": scatter_x,
        "scatter_y": scatter_y,
        "point_label": label,
        "sample_title": f"{label} sample {sample_idx + 1}",
        "image_count": len(image_uris),
        "primary_image_index": 0,
        "view_mode": "interactive-scatter-demo",
    }
    return {
        "image_uris": image_uris,
        "metadata": metadata,
        "label": label,
    }


def _create_dataset(client: httpx.Client) -> str:
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
        "view_mode": {
            "type": "string",
            "description": "Marks this dataset as a multi-image scatter demo seed.",
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
            "dataset_type": "image_classification",
            "task_spec": {
                "task_type": "classification",
                "label_space": LABELS,
                "metadata_schema": metadata_schema,
            },
        },
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"dataset creation failed: {response.status_code} {response.text}"
        )
    return str(response.json()["id"])


def _create_samples(
    client: httpx.Client,
    dataset_id: str,
    samples: int,
    images_per_sample: int,
) -> tuple[int, list[str]]:
    response = api_request(client, "get", f"/api/v1/datasets/{dataset_id}/samples")
    existing = (
        response.json() if response.status_code == 200 else {"total": 0, "items": []}
    )
    if int(existing.get("total", 0)) > 0:
        items = existing.get("items", [])
        return int(existing.get("total", 0)), [str(item.get("id")) for item in items]

    payload = {
        "items": [_build_sample_item(idx, images_per_sample) for idx in range(samples)]
    }
    response = api_request(
        client,
        "post",
        f"/api/v1/datasets/{dataset_id}/samples/import",
        json=payload,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"sample import failed: {response.status_code} {response.text}"
        )
    body = response.json()
    return int(body.get("imported", 0)), [
        str(sample_id) for sample_id in body.get("sample_ids", [])
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed a multi-image scatter demo dataset"
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
        "--samples",
        type=int,
        default=18,
        help="Number of scatter points/samples to create",
    )
    parser.add_argument(
        "--images-per-sample",
        type=int,
        default=3,
        help="Number of images to attach to each sample",
    )
    args = parser.parse_args()

    if args.samples < 1:
        print("ERROR: --samples must be >= 1")
        return 1
    if args.images_per_sample < 2:
        print("ERROR: --images-per-sample must be >= 2 for a multi-image demo")
        return 1

    client = httpx.Client(base_url=args.api_url.rstrip("/"), timeout=30.0)

    print("[0/6] Waiting for API readiness ...")
    try:
        wait_for_api_ready(client)
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1

    print("[1/6] Registering seed user ...")
    response = register_seed_user(client, SEED_EMAIL, SEED_PASSWORD, SEED_NAME)
    if response.status_code == 201:
        print(f"  Created user: {SEED_EMAIL}")
    elif response.status_code == 409:
        print("  User already exists, skipping.")
    else:
        print(f"ERROR: register returned {response.status_code}: {response.text}")
        return 1

    print("[2/6] Promoting to superadmin ...")
    if args.no_promote:
        print("  Skipped (--no-promote).")
    else:
        promote_superadmin(args.compose_file, SEED_EMAIL, SEED_PASSWORD, SEED_NAME)

    print("[3/6] Logging in ...")
    response = login_seed_user(client, SEED_EMAIL, SEED_PASSWORD)
    if response.status_code != 200:
        print(f"ERROR: login failed: {response.status_code} {response.text}")
        return 1
    client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"

    print("[4/6] Resolving organization ...")
    org_id = resolve_or_create_org(client, ORG_NAME, ORG_SLUG)
    if org_id is None:
        print("ERROR: failed to resolve organization")
        return 1
    client.headers["X-Organization-ID"] = org_id
    print(f"  Using org: {org_id}")

    print(f"[5/6] Creating/finding dataset '{DATASET_NAME}' ...")
    try:
        dataset_id = _create_dataset(client)
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"  Dataset ID: {dataset_id}")

    print("[6/6] Creating multi-image samples ...")
    try:
        sample_count, sample_ids = _create_samples(
            client,
            dataset_id,
            args.samples,
            args.images_per_sample,
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1

    print("\nSummary")
    print(f"  Dataset: {DATASET_NAME}")
    print(f"  Dataset ID: {dataset_id}")
    print(f"  Samples: {sample_count}")
    print(f"  Images/sample: {args.images_per_sample}")
    if sample_ids:
        print(f"  First sample ID: {sample_ids[0]}")
    print("  Coordinate metadata keys: scatter_x, scatter_y")
    return 0


if __name__ == "__main__":
    sys.exit(main())
