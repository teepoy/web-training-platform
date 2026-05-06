#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "httpx",
# ]
# ///
"""Seed a deterministic wafer-coordinate demo dataset.

Usage::

    make seed-wafer-demo
    make seed-wafer-demo ARGS="--samples 200000 --batch-size 5000 --reset"

Creates or updates the distinct "Wafer Demo" dataset with deterministic wafer
coordinates stored in sample metadata for wafer-map frontend demos.
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

DATASET_NAME = "Wafer Demo"
DATASET_LABELS = ["wafer-point"]
RANDOM_SEED = 42
WAFER_RADIUS_NM = 150_000_000
PLACEHOLDER_IMAGE_URI: str | None = None


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


def _placeholder_image_uri() -> str:
    global PLACEHOLDER_IMAGE_URI
    if PLACEHOLDER_IMAGE_URI is None:
        PLACEHOLDER_IMAGE_URI = _png_data_uri(16, 73, 109, 137)
    return PLACEHOLDER_IMAGE_URI


def _wafer_coordinates(sample_idx: int) -> tuple[float, float]:
    rng = random.Random(RANDOM_SEED + sample_idx)
    radius_squared = WAFER_RADIUS_NM * WAFER_RADIUS_NM
    while True:
        wafer_x = float(rng.uniform(-WAFER_RADIUS_NM, WAFER_RADIUS_NM))
        wafer_y = float(rng.uniform(-WAFER_RADIUS_NM, WAFER_RADIUS_NM))
        if (wafer_x * wafer_x) + (wafer_y * wafer_y) <= radius_squared:
            return wafer_x, wafer_y


def _build_sample_item(sample_idx: int) -> dict[str, object]:
    wafer_x, wafer_y = _wafer_coordinates(sample_idx)
    metadata = {
        "wafer_x": wafer_x,
        "wafer_y": wafer_y,
        "wafer_index": sample_idx,
        "point_id": f"wafer-point-{sample_idx + 1:06d}",
        "seed": RANDOM_SEED,
    }
    return {
        "image_uris": [_placeholder_image_uri()],
        "metadata": metadata,
    }


def _metadata_schema() -> dict[str, dict[str, str]]:
    return {
        "wafer_x": {
            "type": "float",
            "description": "Wafer X coordinate in nanometers within the wafer disk (radius 150_000_000 nm).",
        },
        "wafer_y": {
            "type": "float",
            "description": "Wafer Y coordinate in nanometers within the wafer disk (radius 150_000_000 nm).",
        },
        "wafer_index": {
            "type": "integer",
            "description": "Deterministic zero-based sample index for wafer demo regeneration.",
        },
        "point_id": {
            "type": "string",
            "description": "Stable point identifier for wafer map drill-down and debugging.",
        },
        "seed": {
            "type": "integer",
            "description": "PRNG seed used to regenerate the deterministic wafer point.",
        },
    }


def _list_datasets(client: httpx.Client) -> list[dict]:
    response = api_request(client, "get", "/api/v1/datasets")
    if response.status_code != 200:
        raise RuntimeError(
            f"dataset list failed: {response.status_code} {response.text}"
        )
    return response.json()


def _get_dataset_sample_total(client: httpx.Client, dataset_id: str) -> int:
    response = api_request(
        client,
        "get",
        f"/api/v1/datasets/{dataset_id}/samples",
        params={"offset": 0, "limit": 1},
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"sample list failed: {response.status_code} {response.text}"
        )
    return int(response.json().get("total", 0))


def _delete_dataset(client: httpx.Client, dataset_id: str) -> None:
    response = api_request(client, "delete", f"/api/v1/datasets/{dataset_id}")
    if response.status_code != 204:
        raise RuntimeError(
            f"dataset delete failed: {response.status_code} {response.text}"
        )


def _create_dataset(client: httpx.Client) -> str:
    response = api_request(
        client,
        "post",
        "/api/v1/datasets",
        json={
            "name": DATASET_NAME,
            "dataset_type": "image_classification",
            "task_spec": {
                "task_type": "classification",
                "label_space": DATASET_LABELS,
                "metadata_schema": _metadata_schema(),
            },
        },
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"dataset creation failed: {response.status_code} {response.text}"
        )
    return str(response.json()["id"])


def _ensure_dataset(client: httpx.Client, reset: bool) -> tuple[str, int]:
    existing = _find_by_name(_list_datasets(client), DATASET_NAME)
    if existing is not None and reset:
        _delete_dataset(client, str(existing["id"]))
        existing = None

    if existing is None:
        dataset_id = _create_dataset(client)
        return dataset_id, 0

    dataset_id = str(existing["id"])
    return dataset_id, _get_dataset_sample_total(client, dataset_id)


def _import_sample_batch(
    client: httpx.Client, dataset_id: str, start_idx: int, batch_size: int
) -> int:
    payload = {
        "items": [
            _build_sample_item(sample_idx)
            for sample_idx in range(start_idx, start_idx + batch_size)
        ]
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
    return int(body.get("imported", 0))


def _seed_samples(
    client: httpx.Client, dataset_id: str, existing_total: int, target_total: int, batch_size: int
) -> tuple[int, bool]:
    if existing_total == target_total:
        return existing_total, True
    if existing_total > target_total:
        print(
            "SKIPPED: dataset already exceeds requested sample count "
            f"({existing_total} > {target_total})"
        )
        return existing_total, True

    current_total = existing_total
    while current_total < target_total:
        chunk_size = min(batch_size, target_total - current_total)
        imported = _import_sample_batch(client, dataset_id, current_total, chunk_size)
        current_total += imported
        if imported != chunk_size:
            raise RuntimeError(
                f"sample import mismatch: expected {chunk_size}, imported {imported}"
            )
    return current_total, False


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the Wafer Demo dataset")
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
        default=200000,
        help="Number of wafer-coordinate samples to ensure",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5000,
        help="Number of samples per bulk import request",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the existing Wafer Demo dataset before recreating it",
    )
    args = parser.parse_args()

    if args.samples < 1:
        print("ERROR: --samples must be >= 1")
        return 1
    if args.batch_size < 1:
        print("ERROR: --batch-size must be >= 1")
        return 1

    client = httpx.Client(base_url=args.api_url.rstrip("/"), timeout=60.0)

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

    print(f"[5/6] Ensuring dataset '{DATASET_NAME}' ...")
    try:
        dataset_id, existing_total = _ensure_dataset(client, reset=args.reset)
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"  Dataset ID: {dataset_id}")
    print(f"  Existing samples: {existing_total}")

    print("[6/6] Importing wafer-coordinate samples ...")
    try:
        total_samples, skipped = _seed_samples(
            client,
            dataset_id,
            existing_total=existing_total,
            target_total=args.samples,
            batch_size=args.batch_size,
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1

    if skipped and total_samples == args.samples:
        print("SKIPPED: dataset already seeded")

    print(f"DATASET_ID: {dataset_id}")
    print(f"TOTAL_SAMPLES: {total_samples}")
    print(f"TOTAL_POINTS: {total_samples}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
