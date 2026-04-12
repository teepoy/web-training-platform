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
import base64
import io
import sys
import time
import uuid

import httpx
from minio import Minio
from PIL import Image

API_URL = "http://localhost:8000"
SEED_EMAIL = "seed@example.com"
SEED_PASSWORD = "seed1234"
DEFAULT_TIMEOUT = 180
DEFAULT_DATASET_NAME = "Smoke Training Dataset"
DEFAULT_PRESET_ID = "resnet50-cls-v1"
MINIO_ENDPOINT = "localhost:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"
MINIO_BUCKET = "finetune-artifacts"


def _fail(message: str) -> int:
    print(f"ERROR: {message}")
    return 1


def _wait_for_health(client: httpx.Client, timeout: int) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            response = client.get(f"{API_URL}/health")
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise RuntimeError("API health check timed out")


def _login(client: httpx.Client) -> str:
    response = client.post(
        f"{API_URL}/api/v1/auth/login",
        json={"email": SEED_EMAIL, "password": SEED_PASSWORD},
    )
    response.raise_for_status()
    return str(response.json()["access_token"])


def _get_first_org_id(client: httpx.Client, headers: dict[str, str]) -> str:
    response = client.get(f"{API_URL}/api/v1/organizations", headers=headers)
    response.raise_for_status()
    orgs = response.json()
    if not isinstance(orgs, list) or not orgs:
        raise RuntimeError("No organizations available for smoke user")
    return str(orgs[0]["id"])


def _data_uri(color: tuple[int, int, int]) -> str:
    image = Image.new("RGB", (8, 8), color=color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _create_dataset(client: httpx.Client, headers: dict[str, str], name: str) -> str:
    response = client.post(
        f"{API_URL}/api/v1/datasets",
        headers=headers,
        json={
            "name": name,
            "dataset_type": "image_classification",
            "task_spec": {"task_type": "classification", "label_space": ["red", "blue"]},
        },
    )
    response.raise_for_status()
    return str(response.json()["id"])


def _create_sample(client: httpx.Client, dataset_id: str, headers: dict[str, str], image_uri: str) -> str:
    response = client.post(
        f"{API_URL}/api/v1/datasets/{dataset_id}/samples",
        headers=headers,
        json={"image_uris": [image_uri], "metadata": {}},
    )
    response.raise_for_status()
    return str(response.json()["id"])


def _create_annotation(client: httpx.Client, sample_id: str, label: str, headers: dict[str, str]) -> None:
    response = client.post(
        f"{API_URL}/api/v1/annotations",
        headers=headers,
        json={"sample_id": sample_id, "label": label, "created_by": "seed-user"},
    )
    response.raise_for_status()


def _create_training_job(client: httpx.Client, dataset_id: str, headers: dict[str, str], preset_id: str) -> str:
    response = client.post(
        f"{API_URL}/api/v1/training-jobs",
        headers=headers,
        json={"dataset_id": dataset_id, "preset_id": preset_id, "created_by": "seed-user"},
    )
    response.raise_for_status()
    return str(response.json()["id"])


def _poll_training_job(client: httpx.Client, job_id: str, headers: dict[str, str], timeout: int) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"{API_URL}/api/v1/training-jobs/{job_id}", headers=headers)
        response.raise_for_status()
        body = response.json()
        status = str(body.get("status", ""))
        if status in {"completed", "failed", "cancelled"}:
            return body
        time.sleep(2)
    raise RuntimeError(f"Training job {job_id} timed out")


def _job_events(client: httpx.Client, job_id: str, headers: dict[str, str]) -> list[dict]:
    response = client.get(f"{API_URL}/api/v1/training-jobs/{job_id}/events/history", headers=headers)
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
            raise RuntimeError(f"Training artifact was not stored in shared MinIO bucket: {uri}")
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
            raise RuntimeError(f"Artifact missing from shared MinIO bucket: {uri}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a real dev training smoke test against the local stack")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Overall training timeout in seconds")
    parser.add_argument("--preset-id", default=DEFAULT_PRESET_ID, help="Training preset to use")
    parser.add_argument("--dataset-name-prefix", default=DEFAULT_DATASET_NAME, help="Prefix for the temporary smoke dataset")
    args = parser.parse_args()

    with httpx.Client(timeout=30.0) as client:
        try:
            print("[1/7] Waiting for API health ...")
            _wait_for_health(client, timeout=args.timeout)

            print("[2/7] Logging in as seed user ...")
            token = _login(client)
            headers = {"Authorization": f"Bearer {token}"}

            print("[3/7] Resolving org context ...")
            headers["X-Organization-ID"] = _get_first_org_id(client, headers)

            dataset_name = f"{args.dataset_name_prefix} {uuid.uuid4().hex[:8]}"
            print("[4/7] Creating tiny labeled dataset ...")
            dataset_id = _create_dataset(client, headers, dataset_name)
            sample_red = _create_sample(client, dataset_id, headers, _data_uri((255, 0, 0)))
            sample_blue = _create_sample(client, dataset_id, headers, _data_uri((0, 0, 255)))
            _create_annotation(client, sample_red, "red", headers)
            _create_annotation(client, sample_blue, "blue", headers)

            print("[5/7] Starting real training job ...")
            job_id = _create_training_job(client, dataset_id, headers, args.preset_id)

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
