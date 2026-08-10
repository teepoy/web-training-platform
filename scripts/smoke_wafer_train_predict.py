#!/usr/bin/env python3
"""Live smoke for seedmaker SC images and the combined train/predict workflow.

Creates a UUID-named db-full dataset, uploads deterministic wafer seed images,
adds two active labels, and verifies train -> model artifact -> predict ->
prediction persistence against the running local stack.
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps/api"))

from app.modules.sc.wafer_data_gen import build_patch_sample  # noqa: E402
from smoke_common import login_seed_user, resolve_seed_org  # noqa: E402

DEFAULT_API_URL = "http://localhost:8000"
LABELS = ("Scratch", "Particle")


def _create_dataset(
    client: httpx.Client,
    *,
    name: str,
) -> str:
    response = client.post(
        "/api/v1/datasets",
        json={
            "name": name,
            "dataset_type": "image_sc",
            "task_spec": {
                "task_type": "sc",
                "label_space": list(LABELS),
            },
        },
    )
    response.raise_for_status()
    return str(response.json()["id"])


def _seed_labeled_samples(
    client: httpx.Client,
    *,
    dataset_id: str,
    sample_count: int,
) -> None:
    for index in range(sample_count):
        patch_sample = build_patch_sample(index)
        sample_response = client.post(
            f"/api/v1/datasets/{dataset_id}/samples",
            json={
                "image_uris": [image.image_id for image in patch_sample.shard_images],
                "metadata": {
                    "sample_id": patch_sample.sample_id,
                    "inspection_time": patch_sample.inspection_time.isoformat()
                    if patch_sample.inspection_time
                    else "",
                    "wafer_key": patch_sample.wafer_key,
                    "defect_id": patch_sample.defect_id,
                    "wafer_x": patch_sample.wafer_x,
                    "wafer_y": patch_sample.wafer_y,
                    "rough_bin": patch_sample.rough_bin,
                    "class_number": patch_sample.class_number,
                    "shard_images": [
                        image.model_dump(mode="json")
                        for image in patch_sample.shard_images
                    ],
                },
            },
        )
        sample_response.raise_for_status()
        annotation_response = client.post(
            "/api/v1/annotations",
            json={
                "dataset_id": dataset_id,
                "sample_id": str(sample_response.json()["id"]),
                "label": LABELS[index % len(LABELS)],
            },
        )
        annotation_response.raise_for_status()


def _related_prediction_jobs(
    client: httpx.Client,
    *,
    dataset_id: str,
    training_job_id: str,
) -> list[dict]:
    response = client.get(
        "/api/v1/prediction-jobs",
        params={"dataset_id": dataset_id},
    )
    response.raise_for_status()
    payload = response.json()
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise RuntimeError("prediction jobs response did not contain an items list")
    return [
        item
        for item in items
        if isinstance(item, dict)
        if item.get("summary", {}).get("source_training_job_id") == training_job_id
    ]


def _wait_for_workflow(
    client: httpx.Client,
    *,
    dataset_id: str,
    job_id: str,
    expected_predictions: int,
    timeout: int,
) -> None:
    deadline = time.monotonic() + timeout
    last_messages: list[str] = []
    while time.monotonic() < deadline:
        job_response = client.get(f"/api/v1/training-jobs/{job_id}")
        job_response.raise_for_status()
        job = job_response.json()
        events_response = client.get(
            f"/api/v1/training-jobs/{job_id}/events/history",
            params={"limit": 100},
        )
        events_response.raise_for_status()
        events = events_response.json()["items"]
        messages = [str(event["message"]) for event in events]
        if messages != last_messages:
            print(
                f"training_status={job['status']} events={messages[-3:]}",
                flush=True,
            )
            last_messages = messages

        if "SC prediction failed; trained model remains available" in messages:
            raise RuntimeError(f"prediction failed: {events[-1]}")
        if job["status"] == "failed":
            raise RuntimeError(f"training failed: {events[-3:]}")
        if "SC prediction completed" not in messages:
            time.sleep(2)
            continue

        artifacts = job.get("artifact_refs") or []
        if not any(item.get("kind") == "model" for item in artifacts):
            raise RuntimeError("training completed without a model artifact")
        prediction_jobs = _related_prediction_jobs(
            client,
            dataset_id=dataset_id,
            training_job_id=job_id,
        )
        if not prediction_jobs or prediction_jobs[0].get("status") != "completed":
            raise RuntimeError(
                f"prediction job did not complete: {prediction_jobs[:1]}"
            )
        latest_response = client.get(
            f"/api/v1/datasets/{dataset_id}/latest-predictions"
        )
        latest_response.raise_for_status()
        latest = latest_response.json()
        if len(latest) != expected_predictions:
            raise RuntimeError(
                "prediction persistence mismatch: "
                f"expected={expected_predictions} got={len(latest)}"
            )
        print(
            f"Smoke test passed: artifacts={len(artifacts)} predictions={len(latest)}",
            flush=True,
        )
        return

    raise RuntimeError("train-and-predict smoke timed out")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run seedmaker wafer images through live train-and-predict"
    )
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--samples", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    if args.samples < 2:
        raise ValueError("--samples must be at least 2")

    token = login_seed_user(args.api_url)
    org_id = resolve_seed_org(args.api_url, token)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Organization-ID": org_id,
    }
    dataset_name = f"Wafer Train Predict Smoke {uuid.uuid4().hex[:8]}"

    with httpx.Client(
        base_url=args.api_url,
        headers=headers,
        timeout=60.0,
    ) as client:
        dataset_id = _create_dataset(client, name=dataset_name)
        print(f"dataset_id={dataset_id}", flush=True)
        _seed_labeled_samples(
            client,
            dataset_id=dataset_id,
            sample_count=args.samples,
        )
        submit_response = client.post(
            "/api/v1/training-jobs/train-and-predict",
            json={
                "dataset_id": dataset_id,
                "trainer_id": "yolo-sc-v1",
            },
        )
        submit_response.raise_for_status()
        submit = submit_response.json()
        job_id = str(submit["train_job"]["id"])
        print(
            f"job_id={job_id} workflow_run_id={submit['workflow_run_id']}",
            flush=True,
        )
        _wait_for_workflow(
            client,
            dataset_id=dataset_id,
            job_id=job_id,
            expected_predictions=args.samples,
            timeout=args.timeout,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
