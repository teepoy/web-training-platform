#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "httpx",
# ]
# ///
from __future__ import annotations

import argparse
import sys
import time

import httpx

API_URL = "http://localhost:8000"
SEED_EMAIL = "seed@example.com"
SEED_PASSWORD = "seed1234"
DATASET_NAME = "ImageNet-1K"


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


def _get_org_id(client: httpx.Client, headers: dict[str, str]) -> str:
    response = client.get(f"{API_URL}/api/v1/organizations", headers=headers)
    response.raise_for_status()
    orgs = response.json()
    if not orgs:
        raise RuntimeError("No organizations available for smoke user")
    return str(orgs[0]["id"])


def _find_seeded_dataset(client: httpx.Client, headers: dict[str, str]) -> dict:
    response = client.get(f"{API_URL}/api/v1/datasets", headers=headers)
    response.raise_for_status()
    for dataset in response.json():
        if dataset.get("name") == DATASET_NAME:
            return dataset
    raise RuntimeError(f"Seeded dataset '{DATASET_NAME}' not found. Run `make seed-imagenet-dev` first.")


def _find_seeded_model(client: httpx.Client, dataset_id: str, headers: dict[str, str]) -> dict:
    response = client.get(f"{API_URL}/api/v1/models?dataset_id={dataset_id}", headers=headers)
    response.raise_for_status()
    models = response.json()
    if not models:
        raise RuntimeError("No seeded model found for ImageNet dataset")
    return models[0]


def _poll_prediction_job(client: httpx.Client, job_id: str, headers: dict[str, str], timeout: int) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"{API_URL}/api/v1/prediction-jobs/{job_id}", headers=headers)
        response.raise_for_status()
        body = response.json()
        status = str(body.get("status", ""))
        if status in {"completed", "failed", "cancelled"}:
            return body
        time.sleep(2)
    raise RuntimeError(f"Prediction job {job_id} timed out")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a dev batch smoke test against the local stack")
    parser.add_argument("--timeout", type=int, default=180, help="Per-step timeout in seconds")
    args = parser.parse_args()

    with httpx.Client(timeout=30.0) as client:
        try:
            print("[1/6] Waiting for API health ...")
            _wait_for_health(client, timeout=args.timeout)

            print("[2/6] Logging in as seed user ...")
            token = _login(client)
            headers = {"Authorization": f"Bearer {token}"}

            print("[3/6] Resolving org context ...")
            org_id = _get_org_id(client, headers)
            headers["X-Organization-ID"] = org_id

            print("[4/6] Locating seeded dataset/model ...")
            dataset = _find_seeded_dataset(client, headers)
            model = _find_seeded_model(client, str(dataset["id"]), headers)

            print("[5/6] Starting batch prediction job ...")
            predict_response = client.post(
                f"{API_URL}/api/v1/predictions/run",
                headers=headers,
                json={
                    "dataset_id": dataset["id"],
                    "model_id": model["id"],
                    "target": dataset["dataset_type"],
                },
            )
            predict_response.raise_for_status()
            prediction_job = _poll_prediction_job(client, str(predict_response.json()["id"]), headers, args.timeout)
            if prediction_job.get("status") != "completed":
                return _fail(f"Prediction job ended with status={prediction_job.get('status')}")

            print("[6/6] Starting feature extraction job ...")
            feature_response = client.post(
                f"{API_URL}/api/v1/datasets/{dataset['id']}/features/extract",
                headers=headers,
            )
            feature_response.raise_for_status()
            feature_job = _poll_prediction_job(client, str(feature_response.json()["id"]), headers, args.timeout)
            if feature_job.get("status") != "completed":
                return _fail(f"Feature extraction job ended with status={feature_job.get('status')}")

            prediction_summary = prediction_job.get("summary", {})
            feature_summary = feature_job.get("summary", {})
            print("Smoke test passed")
            print(f"prediction_processed={prediction_summary.get('processed')}")
            print(f"feature_processed={feature_summary.get('processed')}")
            return 0
        except Exception as exc:
            return _fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
