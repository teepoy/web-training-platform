#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "httpx",
#     "pillow",
# ]
# ///
from __future__ import annotations

import argparse
import base64
import io
import time
import uuid

import httpx
from PIL import Image

API_URL = "http://localhost:8000"
SEED_EMAIL = "seed@example.com"
SEED_PASSWORD = "seed1234"
DEFAULT_TIMEOUT = 240
DEFAULT_DATASET_NAME = "Smoke Prediction Dataset"
DEFAULT_PRESET_ID = "resnet50-cls-v1"


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
        if str(body.get("status", "")) in {"completed", "failed", "cancelled"}:
            return body
        time.sleep(2)
    raise RuntimeError(f"Training job {job_id} timed out")


def _find_model_for_job(client: httpx.Client, dataset_id: str, job_id: str, headers: dict[str, str]) -> dict:
    response = client.get(f"{API_URL}/api/v1/models?dataset_id={dataset_id}", headers=headers)
    response.raise_for_status()
    models = response.json()
    if not isinstance(models, list):
        raise RuntimeError("Model list response was not a list")
    for model in models:
        if str(model.get("job_id", "")) == job_id:
            return model
    raise RuntimeError(f"No model found for completed training job {job_id}")


def _create_prediction_job(
    client: httpx.Client,
    dataset_id: str,
    model_id: str,
    sample_ids: list[str],
    headers: dict[str, str],
) -> str:
    response = client.post(
        f"{API_URL}/api/v1/predictions/run",
        headers=headers,
        json={
            "dataset_id": dataset_id,
            "model_id": model_id,
            "sample_ids": sample_ids,
            "target": "image_classification",
        },
    )
    response.raise_for_status()
    return str(response.json()["id"])


def _poll_prediction_job(client: httpx.Client, job_id: str, headers: dict[str, str], timeout: int) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"{API_URL}/api/v1/prediction-jobs/{job_id}", headers=headers)
        response.raise_for_status()
        body = response.json()
        if str(body.get("status", "")) in {"completed", "failed", "cancelled"}:
            return body
        time.sleep(2)
    raise RuntimeError(f"Prediction job {job_id} timed out")


def _prediction_events(client: httpx.Client, job_id: str, headers: dict[str, str]) -> list[dict]:
    response = client.get(f"{API_URL}/api/v1/prediction-jobs/{job_id}/events", headers=headers)
    response.raise_for_status()
    body = response.json()
    return body if isinstance(body, list) else []


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a real dev prediction smoke test against the local stack")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Overall timeout in seconds")
    parser.add_argument("--preset-id", default=DEFAULT_PRESET_ID, help="Training preset to use for the temporary model")
    parser.add_argument("--dataset-name-prefix", default=DEFAULT_DATASET_NAME, help="Prefix for the temporary smoke dataset")
    args = parser.parse_args()

    with httpx.Client(timeout=30.0) as client:
        try:
            print("[1/8] Waiting for API health ...")
            _wait_for_health(client, timeout=args.timeout)

            print("[2/8] Logging in as seed user ...")
            token = _login(client)
            headers = {"Authorization": f"Bearer {token}"}

            print("[3/8] Resolving org context ...")
            headers["X-Organization-ID"] = _get_first_org_id(client, headers)

            dataset_name = f"{args.dataset_name_prefix} {uuid.uuid4().hex[:8]}"
            print("[4/8] Creating tiny labeled dataset ...")
            dataset_id = _create_dataset(client, headers, dataset_name)
            sample_red = _create_sample(client, dataset_id, headers, _data_uri((255, 0, 0)))
            sample_blue = _create_sample(client, dataset_id, headers, _data_uri((0, 0, 255)))
            _create_annotation(client, sample_red, "red", headers)
            _create_annotation(client, sample_blue, "blue", headers)
            sample_ids = [sample_red, sample_blue]

            print("[5/8] Training a temporary model ...")
            training_job_id = _create_training_job(client, dataset_id, headers, args.preset_id)
            training_job = _poll_training_job(client, training_job_id, headers, args.timeout)
            if training_job.get("status") != "completed":
                raise RuntimeError(f"Training prerequisite failed with status={training_job.get('status')}")
            model = _find_model_for_job(client, dataset_id, training_job_id, headers)

            print("[6/8] Starting real batch prediction job ...")
            prediction_job_id = _create_prediction_job(client, dataset_id, str(model["id"]), sample_ids, headers)

            print("[7/8] Polling prediction job to terminal state ...")
            prediction_job = _poll_prediction_job(client, prediction_job_id, headers, args.timeout)
            if prediction_job.get("status") != "completed":
                events = _prediction_events(client, prediction_job_id, headers)
                messages = [str(item.get("message", "")) for item in events[-10:]]
                raise RuntimeError(
                    f"Prediction job ended with status={prediction_job.get('status')} recent_events={messages}"
                )

            print("[8/8] Verifying prediction summary ...")
            summary = prediction_job.get("summary", {})
            if int(summary.get("processed", 0)) < len(sample_ids):
                raise RuntimeError(f"Prediction smoke processed too few samples: {summary}")
            if int(summary.get("successful", 0)) < 1:
                raise RuntimeError(f"Prediction smoke produced no successful predictions: {summary}")

            print("Smoke test passed")
            print(f"training_job_id={training_job_id}")
            print(f"prediction_job_id={prediction_job_id}")
            print(f"dataset_id={dataset_id}")
            print(f"model_id={model['id']}")
            print(f"prediction_processed={summary.get('processed')}")
            print(f"prediction_successful={summary.get('successful')}")
            return 0
        except Exception as exc:
            return _fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
