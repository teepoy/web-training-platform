from __future__ import annotations

import time
from typing import Any

import httpx

DEFAULT_COMPOSE_FILE = "infra/compose/docker-compose.yaml"
DEFAULT_SEED_EMAIL = "seed@example.com"
DEFAULT_SEED_PASSWORD = "seed1234"
DEFAULT_SEED_NAME = "Seed Admin"
DEFAULT_ORG_NAME = "Default Org"
DEFAULT_ORG_SLUG = "default-org"


def api_request(
    client: httpx.Client, method: str, path: str, **kwargs: Any
) -> httpx.Response:
    return getattr(client, method)(path, **kwargs)


def wait_for_api_ready(client: httpx.Client, timeout_seconds: float = 120.0) -> None:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            response = client.get("/health")
            if response.status_code == 200:
                return
            last_error = f"unexpected status {response.status_code}"
        except httpx.HTTPError as exc:
            last_error = str(exc)
        time.sleep(2.0)
    raise RuntimeError(f"API not ready after {timeout_seconds:.0f}s: {last_error}")


def _find_by_name(items: list[dict], name: str) -> dict | None:
    for item in items:
        if item.get("name") == name:
            return item
    return None


# ---------------------------------------------------------------------------
# Shared model helpers (used by imagenet seed datasets)
# ---------------------------------------------------------------------------


def delete_model(client: httpx.Client, model_id: str) -> None:
    r = api_request(client, "delete", f"/api/v1/models/{model_id}")
    if r.status_code != 204:
        raise RuntimeError(
            f"failed to delete existing model {model_id}: {r.status_code} {r.text}"
        )


def is_image_classification_compatible(model: dict[str, Any]) -> bool:
    raw_meta = model.get("metadata")
    metadata: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    dataset_types: Any = (
        metadata.get("dataset_types")
        if isinstance(metadata.get("dataset_types"), list)
        else []
    )
    task_types: Any = (
        metadata.get("task_types")
        if isinstance(metadata.get("task_types"), list)
        else []
    )
    prediction_targets: Any = (
        metadata.get("prediction_targets")
        if isinstance(metadata.get("prediction_targets"), list)
        else []
    )
    return (
        "image_classification" in dataset_types
        and "classification" in task_types
        and "image_classification" in prediction_targets
    )


def create_model_via_training_job(
    client: httpx.Client,
    dataset_id: str,
    trainer_id: str,
    job_timeout: int,
) -> tuple[str | None, str | None]:
    """Create a training job via local engine and return (job_id, model_id)."""
    r = api_request(
        client,
        "post",
        "/api/v1/training-jobs",
        json={
            "dataset_id": dataset_id,
            "trainer_id": trainer_id,
        },
    )
    if r.status_code != 200:
        print(f"  ERROR: job creation failed: {r.status_code} {r.text}")
        return None, None
    job_id = r.json()["id"]
    print(f"  Job created: {job_id}, waiting for completion ...")

    t0 = time.time()
    while time.time() - t0 < job_timeout:
        r = api_request(client, "get", f"/api/v1/training-jobs/{job_id}")
        if r.status_code == 200:
            status = r.json().get("status", "")
            if status == "completed":
                print(f"  Job completed in {time.time() - t0:.1f}s")
                break
            if status in ("failed", "cancelled"):
                print(f"  ERROR: job ended with status '{status}'")
                return job_id, None
        time.sleep(1)
    else:
        print(f"  ERROR: job did not complete within {job_timeout}s")
        return job_id, None

    r = api_request(client, "get", f"/api/v1/models?dataset_id={dataset_id}")
    if r.status_code == 200 and r.json():
        model_id = r.json()[0]["id"]
        return job_id, model_id
    return job_id, None
