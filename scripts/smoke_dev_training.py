#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "httpx",
#     "minio",
#     "pillow",
# ]
# ///
from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path

import httpx
from minio import Minio

sys.path.insert(0, str(Path(__file__).parent))
from smoke_common import (
    create_synthetic_image,
    login_seed_user,
    resolve_seed_org,
    wait_for_api_ready,
)

API_URL = "http://localhost:8000"
DEFAULT_TIMEOUT = 180
DEFAULT_DATASET_NAME = "Smoke Training Dataset"
DEFAULT_TRAINER_ID = "resnet50-cls-v1"


def _create_training_job(
    client: httpx.Client, dataset_id: str, headers: dict[str, str], trainer_id: str
) -> str:
    response = client.post(
        f"{API_URL}/api/v1/training-jobs",
        headers=headers,
        json={
            "dataset_id": dataset_id,
            "trainer_id": trainer_id,
            "created_by": "seed-user",
        },
    )
    response.raise_for_status()
    return str(response.json()["id"])


def _create_sample(
    client: httpx.Client, dataset_id: str, headers: dict[str, str], image_uri: str
) -> str:
    response = client.post(
        f"{API_URL}/api/v1/datasets/{dataset_id}/samples",
        headers=headers,
        json={"image_uris": [image_uri], "metadata": {}},
    )
    response.raise_for_status()
    return str(response.json()["id"])


def _create_annotation(
    client: httpx.Client, sample_id: str, label: str, headers: dict[str, str]
) -> None:
    response = client.post(
        f"{API_URL}/api/v1/annotations",
        headers=headers,
        json={"sample_id": sample_id, "label": label, "created_by": "seed-user"},
    )
    response.raise_for_status()


def _create_training_job(
    client: httpx.Client, dataset_id: str, headers: dict[str, str], trainer_id: str
) -> str:
    response = client.post(
        f"{API_URL}/api/v1/training-jobs",
        headers=headers,
        json={
            "dataset_id": dataset_id,
            "trainer_id": trainer_id,
            "created_by": "seed-user",
        },
    )
    response.raise_for_status()
    return str(response.json()["id"])


def _poll_training_job(
    client: httpx.Client, job_id: str, headers: dict[str, str], timeout: int
) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(
            f"{API_URL}/api/v1/training-jobs/{job_id}", headers=headers
        )
        response.raise_for_status()
        body = response.json()
        status = str(body.get("status", ""))
        if status in {"completed", "failed", "cancelled"}:
            return body
        time.sleep(2)
    raise RuntimeError(f"Training job {job_id} timed out")


def _job_events(
    client: httpx.Client, job_id: str, headers: dict[str, str]
) -> list[dict]:
    response = client.get(
        f"{API_URL}/api/v1/training-jobs/{job_id}/events/history", headers=headers
    )
    response.raise_for_status()
    body = response.json()
    items = body.get("items") if isinstance(body, dict) else None
    return items if isinstance(items, list) else []


def _assert_s3_artifacts(job: dict) -> list[str]:
    artifact_refs = job.get("artifact_refs")
    if not isinstance(artifact_refs, list) or not artifact_refs:
        raise RuntimeError("Training job completed without artifact_refs")
    uris: list[str] = []
    for artifact in artifact_refs:
        uri = str(artifact.get("uri", ""))
        if not uri.startswith(f"s3://{MINIO_BUCKET}/"):
            raise RuntimeError(
                f"Training artifact was not stored in shared MinIO bucket: {uri}"
            )
        uris.append(uri)
    return uris


def _assert_minio_objects_exist(uris: list[str]) -> None:
    client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )
    for uri in uris:
        object_name = uri.removeprefix(f"s3://{MINIO_BUCKET}/")
        try:
            client.stat_object(MINIO_BUCKET, object_name)
        except Exception as exc:
            raise RuntimeError(
                f"Artifact missing from shared MinIO bucket: {uri}"
            ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a real dev training smoke test against the local stack"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="Overall training timeout in seconds",
    )
    parser.add_argument(
        "--trainer-id", default=DEFAULT_TRAINER_ID, help="Trainer to use"
    )
    parser.add_argument(
        "--dataset-name-prefix",
        default=DEFAULT_DATASET_NAME,
        help="Prefix for the temporary smoke dataset",
    )
    args = parser.parse_args()

    try:
        print("[1/7] Waiting for API health ...")
        wait_for_api_ready(API_URL, timeout=args.timeout)

        print("[2/7] Logging in as seed user ...")
        token = login_seed_user(API_URL)
        headers = {"Authorization": f"Bearer {token}"}

        print("[3/7] Resolving org context ...")
        headers["X-Organization-ID"] = resolve_seed_org(API_URL, token)

        with httpx.Client(timeout=30.0) as client:
            dataset_name = f"{args.dataset_name_prefix} {uuid.uuid4().hex[:8]}"
            print("[4/7] Creating tiny labeled dataset ...")
            dataset_id = _create_dataset(client, headers, dataset_name)
            sample_red = _create_sample(
                client, dataset_id, headers, create_synthetic_image("red")
            )
            sample_blue = _create_sample(
                client, dataset_id, headers, create_synthetic_image("blue")
            )
            _create_annotation(client, sample_red, "red", headers)
            _create_annotation(client, sample_blue, "blue", headers)

            print("[5/7] Starting real training job ...")
            job_id = _create_training_job(client, dataset_id, headers, args.trainer_id)

            print("[6/7] Polling job to terminal state ...")
            job = _poll_training_job(client, job_id, headers, args.timeout)
            if job.get("status") != "completed":
                events = _job_events(client, job_id, headers)
                event_messages = [str(item.get("message", "")) for item in events[-10:]]
                raise RuntimeError(
                    f"Training job ended with status={job.get('status')} recent_events={event_messages}"
                )

            print("[7/7] Verifying shared MinIO/S3 artifacts ...")
            artifact_uris = _assert_s3_artifacts(job)
            _assert_minio_objects_exist(artifact_uris)

            print("Smoke test passed")
            print(f"job_id={job_id}")
            print(f"dataset_id={dataset_id}")
            print(f"artifacts={len(artifact_uris)}")
            for uri in artifact_uris:
                print(uri)
            return 0
    except Exception as exc:
        return _fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
