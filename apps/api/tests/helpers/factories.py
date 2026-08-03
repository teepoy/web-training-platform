from __future__ import annotations

import base64
import io
import time
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import TRAINER_ID


def pytest_auth_headers() -> dict[str, str]:
    """Return auth headers compatible with conftest's mocked auth dependencies.

    When the ``_mock_auth_deps`` autouse fixture is active (the default),
    these headers are redundant — the dependency overrides inject a test user
    regardless of what the Authorization header contains.  This helper exists
    so tests that send explicit headers (or factories used outside
    ``_mock_auth_deps``) have a consistent token.
    """
    return {"Authorization": "Bearer test-token"}


# ---------------------------------------------------------------------------
# Synthetic image helpers
# ---------------------------------------------------------------------------


def _default_image_uri_generator() -> str:
    """Generate a tiny 1×1 gray PNG as a base64 data URI.

    Intended as the default ``image_uri_generator`` for
    :func:`create_test_samples` so callers don't need Pillow themselves.
    """
    from PIL import Image

    img = Image.new("RGB", (1, 1), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"


# ---------------------------------------------------------------------------
# Dataset factories
# ---------------------------------------------------------------------------


def create_test_dataset(
    client: TestClient,
    name: str,
    labels: list[str],
    dataset_type: str = "image_classification",
) -> dict[str, Any]:
    """Create a dataset via ``POST /api/v1/datasets``.

    Args:
        client: An active ``TestClient`` instance.
        name: Human-readable dataset name.
        labels: Label space for the dataset (``task_spec.label_space``).
        dataset_type: An implemented dataset type such as
            ``"image_classification"`` or ``"image_sc"``.

    Returns:
        The JSON response dict containing at least ``id``, ``name``,
        ``dataset_type``, and ``task_spec``.

    Raises:
        AssertionError: If the status code is not 200.
    """
    resp = client.post(
        "/api/v1/datasets",
        json={
            "name": name,
            "dataset_type": dataset_type,
            "task_spec": {"task_type": "classification", "label_space": labels},
        },
    )
    assert resp.status_code == 200, (
        f"Failed to create dataset '{name}': "
        f"status={resp.status_code} body={resp.json()}"
    )
    return resp.json()


def get_dataset(client: TestClient, dataset_id: str) -> dict[str, Any]:
    """Fetch a single dataset by id via ``GET /api/v1/datasets/{id}``.

    Raises:
        AssertionError: If the status code is not 200.
    """
    resp = client.get(f"/api/v1/datasets/{dataset_id}")
    assert resp.status_code == 200, (
        f"Failed to get dataset '{dataset_id}': "
        f"status={resp.status_code}"
    )
    return resp.json()


# ---------------------------------------------------------------------------
# Sample factories
# ---------------------------------------------------------------------------


def create_test_samples(
    client: TestClient,
    dataset_id: str,
    count: int,
    image_uri_generator: Callable[[], str] | None = None,
) -> list[dict[str, Any]]:
    """Create *count* samples in a dataset via ``POST /api/v1/datasets/{id}/samples``.

    Args:
        client: An active ``TestClient`` instance.
        dataset_id: Target dataset id.
        count: Number of samples to create.
        image_uri_generator: Callable returning a single image URI (data URI
            or remote URL).  Defaults to a synthetic 1×1 gray PNG data URI.

    Returns:
        List of response dicts, each containing at least ``id`` and
        ``dataset_id``.

    Raises:
        AssertionError: If any sample creation returns a non-200 status.
    """
    if image_uri_generator is None:
        image_uri_generator = _default_image_uri_generator

    samples: list[dict[str, Any]] = []
    for _ in range(count):
        image_uri = image_uri_generator()
        resp = client.post(
            f"/api/v1/datasets/{dataset_id}/samples",
            json={"image_uris": [image_uri], "metadata": {}},
        )
        assert resp.status_code == 200, (
            f"Failed to create sample in dataset '{dataset_id}': "
            f"status={resp.status_code} body={resp.json()}"
        )
        samples.append(resp.json())
    return samples


def list_samples(
    client: TestClient,
    dataset_id: str,
    offset: int = 0,
    limit: int = 1000,
) -> dict[str, Any]:
    """List samples for a dataset via ``GET /api/v1/datasets/{id}/samples``.

    Returns a paginated response dict with ``items`` and ``total`` keys.
    """
    resp = client.get(
        f"/api/v1/datasets/{dataset_id}/samples",
        params={"offset": offset, "limit": limit},
    )
    assert resp.status_code == 200, (
        f"Failed to list samples for dataset '{dataset_id}': "
        f"status={resp.status_code}"
    )
    return resp.json()


# ---------------------------------------------------------------------------
# Annotation factories
# ---------------------------------------------------------------------------


def create_test_annotations(
    client: TestClient,
    sample_ids: list[str],
    labels: list[str],
    *,
    dataset_id: str,
) -> list[dict[str, Any]]:
    """Create annotations for *sample_ids*, cycling through *labels*.

    Each annotation is POSTed to ``/api/v1/annotations`` with ``label`` and
    ``sample_id``.  If there are more samples than labels, labels are reused
    round-robin.

    Args:
        client: An active ``TestClient`` instance.
        sample_ids: Samples to annotate.
        labels: Label pool — cycled if ``len(labels) < len(sample_ids)``.
        dataset_id: Dataset that owns the samples.

    Returns:
        List of response dicts, each containing at least ``id``, ``sample_id``,
        and ``label``.

    Raises:
        AssertionError: If any annotation creation returns a non-200 status.
        ValueError: If *sample_ids* is non-empty but *labels* is empty.
    """
    if sample_ids and not labels:
        raise ValueError("labels must not be empty when sample_ids is non-empty")

    annotations: list[dict[str, Any]] = []
    for i, sid in enumerate(sample_ids):
        label = labels[i % len(labels)]
        resp = client.post(
            "/api/v1/annotations",
            json={"dataset_id": dataset_id, "sample_id": sid, "label": label},
        )
        assert resp.status_code == 200, (
            f"Failed to create annotation for sample '{sid}': "
            f"status={resp.status_code} body={resp.json()}"
        )
        annotations.append(resp.json())
    return annotations


# ---------------------------------------------------------------------------
# Training job factories
# ---------------------------------------------------------------------------


def create_test_training_job(
    client: TestClient,
    dataset_id: str,
    trainer_id: str | None = None,
) -> dict[str, Any]:
    """Create a training job via ``POST /api/v1/training-jobs``.

    Args:
        client: An active ``TestClient`` instance.
        dataset_id: Dataset to train on.
        trainer_id: Trainer id (defaults to ``TRAINER_ID`` from conftest).

    Returns:
        The job response dict containing at least ``id`` and ``status``.

    Raises:
        AssertionError: If the status code is not 200.
    """
    resp = client.post(
        "/api/v1/training-jobs",
        json={
            "dataset_id": dataset_id,
            "trainer_id": trainer_id or TRAINER_ID,
        },
    )
    assert resp.status_code == 200, (
        f"Failed to create training job for dataset '{dataset_id}': "
        f"status={resp.status_code} body={resp.json()}"
    )
    return resp.json()


def get_training_job(client: TestClient, job_id: str) -> dict[str, Any]:
    """Fetch a training job by id via ``GET /api/v1/training-jobs/{id}``.

    Raises:
        AssertionError: If the status code is not 200.
    """
    resp = client.get(f"/api/v1/training-jobs/{job_id}")
    assert resp.status_code == 200, (
        f"Failed to get training job '{job_id}': status={resp.status_code}"
    )
    return resp.json()


# ---------------------------------------------------------------------------
# Job polling
# ---------------------------------------------------------------------------


def wait_for_job_completion(
    client: TestClient,
    job_id: str,
    job_type: str = "training",
    timeout: int = 120,
    poll_interval: float = 2.0,
) -> dict[str, Any]:
    """Poll ``GET /api/v1/{job_type}-jobs/{job_id}`` until the job reaches a
    terminal state.

    Args:
        client: An active ``TestClient`` instance.
        job_id: The job id to poll.
        job_type: ``"training"`` or ``"prediction"`` — determines the URL prefix.
        timeout: Maximum seconds to wait before raising :class:`RuntimeError`.
        poll_interval: Seconds between polls.

    Returns:
        The final job response dict (``status`` will be ``"completed"`` or
        ``"failed"``).

    Raises:
        RuntimeError: If the job fails, or times out without reaching a
            terminal state.
    """
    endpoint = f"/api/v1/{job_type}-jobs/{job_id}"
    deadline = time.monotonic() + timeout
    last_status: str | None = None

    while time.monotonic() < deadline:
        resp = client.get(endpoint)
        if resp.status_code == 404:
            raise RuntimeError(
                f"{job_type} job '{job_id}' not found (404)"
            )
        assert resp.status_code == 200, (
            f"Unexpected status {resp.status_code} polling {job_type} job '{job_id}'"
        )
        body = resp.json()
        status: str = body.get("status", "")
        last_status = status

        if status in ("completed", "failed"):
            return body

        time.sleep(poll_interval)

    raise RuntimeError(
        f"{job_type} job '{job_id}' timed out after {timeout}s "
        f"(last status: {last_status})"
    )


# ---------------------------------------------------------------------------
# Prediction job factories
# ---------------------------------------------------------------------------


def create_test_prediction_job(
    client: TestClient,
    dataset_id: str,
    model_id: str,
    target: str = "image_classification",
) -> dict[str, Any]:
    """Create a prediction job via ``POST /api/v1/predictions/run``.

    In the test profile (``APP_CONFIG_PROFILE=test``) predictions run
    synchronously, so the returned job will already have status
    ``"completed"``.

    Args:
        client: An active ``TestClient`` instance.
        dataset_id: Dataset to run predictions on.
        model_id: Model artifact id.
        target: Prediction target key (default ``"image_classification"``).

    Returns:
        The job response dict containing at least ``id``, ``status``,
        ``dataset_id``, and ``model_id``.

    Raises:
        AssertionError: If the status code is not 202.
    """
    resp = client.post(
        "/api/v1/predictions/run",
        json={
            "model_id": model_id,
            "dataset_id": dataset_id,
            "target": target,
        },
    )
    assert resp.status_code == 202, (
        f"Failed to create prediction job for dataset '{dataset_id}': "
        f"status={resp.status_code} body={resp.json()}"
    )
    return resp.json()


def get_prediction_job(client: TestClient, job_id: str) -> dict[str, Any]:
    """Fetch a prediction job by id via ``GET /api/v1/prediction-jobs/{id}``.

    Raises:
        AssertionError: If the status code is not 200.
    """
    resp = client.get(f"/api/v1/prediction-jobs/{job_id}")
    assert resp.status_code == 200, (
        f"Failed to get prediction job '{job_id}': status={resp.status_code}"
    )
    return resp.json()


# ---------------------------------------------------------------------------
# Model helpers
# ---------------------------------------------------------------------------


def get_model(client: TestClient, model_id: str) -> dict[str, Any]:
    """Fetch a model by id via ``GET /api/v1/models/{id}``.

    Raises:
        AssertionError: If the status code is not 200.
    """
    resp = client.get(f"/api/v1/models/{model_id}")
    assert resp.status_code == 200, (
        f"Failed to get model '{model_id}': status={resp.status_code}"
    )
    return resp.json()
