from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import asyncio
import os

os.environ.setdefault("APP_CONFIG_PROFILE", "test")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///./finetune-test-{uuid4().hex}.db")


# ---------------------------------------------------------------------------
# Auth dependency overrides for existing tests
#
# Existing tests (test_api_flows, test_annotation_crud, etc.) do NOT send
# auth headers.  After T11, all resource routes require auth + org context.
# We override the FastAPI dependencies globally for all non-auth tests so
# existing tests keep passing without modification.
#
# test_auth_routes.py opts OUT of these overrides by clearing them with the
# `no_auth_override` marker — see that file for details.
# ---------------------------------------------------------------------------

import pytest

DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000002"


@pytest.fixture(autouse=True, scope="function")
def _mock_auth_deps(request):
    """Override get_current_user and get_current_org for all tests by default.

    Tests that need real auth enforcement should either:
    - Use the ``no_auth_override`` marker, OR
    - Be in test_auth.py or test_auth_routes.py (automatically skipped)
    """
    # Allow specific tests to opt out of the override
    if request.node.get_closest_marker("no_auth_override"):
        yield
        return

    # Skip override for auth-specific test modules that test real auth behavior
    module_name = getattr(request.module, "__name__", "")
    if module_name in ("test_auth", "test_auth_routes"):
        yield
        return

    from app.main import app
    from app.api.deps import get_current_user, get_current_org
    from app.domain.models import User, Organization
    import datetime

    _mock_user = User(
        id=DEFAULT_USER_ID,
        email="test@test.com",
        name="Test User",
        is_superadmin=True,
        is_active=True,
        created_at=datetime.datetime(2024, 1, 1),
    )
    _mock_org = Organization(
        id=DEFAULT_ORG_ID,
        name="Default",
        slug="default",
        created_at=datetime.datetime(2024, 1, 1),
    )

    app.dependency_overrides[get_current_user] = lambda: _mock_user
    app.dependency_overrides[get_current_org] = lambda: _mock_org
    yield
    # Clean up overrides after each test
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_org, None)


# ---------------------------------------------------------------------------
# Label Studio client override for non-LS tests
#
# After the LS-always-on migration, create_dataset always calls LS to create
# a project.  Non-LS tests don't mock LS themselves, so we provide a global
# mock that succeeds silently.  Tests in test_ls_*.py manage their own
# overrides — they call container.label_studio_client.override() directly
# and reset it in their finally blocks.
# ---------------------------------------------------------------------------

from unittest.mock import AsyncMock, MagicMock
from dependency_injector import providers


@pytest.fixture(autouse=True, scope="function")
def _mock_ls_client(request):
    """Override the LS client for all tests by default.

    Tests that manage their own LS client overrides (test_ls_* modules) opt
    out via the ``no_ls_override`` marker or by being in a module whose name
    starts with ``test_ls_``.
    """
    if request.node.get_closest_marker("no_ls_override"):
        yield
        return

    module_name = getattr(request.module, "__name__", "").rsplit(".", 1)[-1]
    if module_name.startswith("test_ls_") or module_name == "test_label_studio_client":
        yield
        return

    from app.main import container

    _mock_ls = MagicMock()
    _mock_ls.create_project = AsyncMock(return_value={"id": 1, "title": "mock-project"})
    _mock_ls.update_project = AsyncMock(return_value={"id": 1, "title": "mock-project"})
    _mock_ls.delete_project = AsyncMock(return_value=None)
    _mock_ls.create_task = AsyncMock(return_value={"id": 1})
    _mock_ls.import_tasks = AsyncMock(side_effect=lambda project_id, tasks, return_task_ids=True: {
        "task_ids": list(range(1, len(tasks) + 1)),
        "task_count": len(tasks),
    })
    _mock_ls.create_annotation = AsyncMock(return_value={"id": 0, "task": 0, "result": []})
    _mock_ls.list_tasks = AsyncMock(return_value=([], 0))
    _mock_ls.list_annotations = AsyncMock(return_value=[])
    _mock_ls.export_project = AsyncMock(return_value=[])

    container.label_studio_client.override(providers.Object(_mock_ls))
    yield
    container.label_studio_client.reset_override()


@pytest.fixture(autouse=True, scope="function")
def _mock_embedding_service(request):
    """Override the embedding service for tests by default.

    Feature extraction and related endpoints otherwise depend on an external
    gRPC embedding server, which can make the test suite block indefinitely
    when that service is unavailable.
    """
    if request.node.get_closest_marker("no_embedding_override"):
        yield
        return

    from app.main import container

    async def _embed_image(image_bytes: bytes, model_name: str = "openai/clip-vit-base-patch32") -> list[float]:
        size = max(1, len(image_bytes))
        base = min(1.0, size / 255.0)
        return [base, 0.5, 0.25, 0.125]

    async def _embed_batch(image_bytes_list: list[bytes], model_name: str = "openai/clip-vit-base-patch32") -> list[list[float]]:
        return [await _embed_image(image_bytes, model_name=model_name) for image_bytes in image_bytes_list]

    async def _classify_image(
        image_bytes: bytes,
        labels: list[str],
        model_name: str = "openai/clip-vit-base-patch32",
    ) -> tuple[str, float, dict[str, float]]:
        if not labels:
            return "", 0.0, {}
        score = 1.0 / len(labels)
        scores = {label: score for label in labels}
        return labels[0], score, scores

    async def _classify_batch(
        image_bytes_list: list[bytes],
        labels: list[str],
        model_name: str = "openai/clip-vit-base-patch32",
    ) -> list[tuple[str, float, dict[str, float]]]:
        return [await _classify_image(image_bytes, labels, model_name=model_name) for image_bytes in image_bytes_list]

    _mock_embedding = MagicMock()
    _mock_embedding.embed_image = AsyncMock(side_effect=_embed_image)
    _mock_embedding.embed_batch = AsyncMock(side_effect=_embed_batch)
    _mock_embedding.classify_image = AsyncMock(side_effect=_classify_image)
    _mock_embedding.classify_batch = AsyncMock(side_effect=_classify_batch)
    _mock_embedding.health = AsyncMock(return_value=True)

    container.embedding_service.override(providers.Object(_mock_embedding))
    yield
    container.embedding_service.reset_override()


# ---------------------------------------------------------------------------
# Inference worker override for non-worker tests
#
# Flow tasks in predict_job.py call the inference worker HTTP client for
# batch prediction/embedding.  This mock provides deterministic responses
# so tests can exercise worker-side flow functions without a running
# inference service.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True, scope="function")
def _mock_inference_worker(request):
    """Override the inference worker client for all tests by default.

    Tests that need a real (or custom) inference worker should use the
    ``no_inference_override`` marker.
    """
    if request.node.get_closest_marker("no_inference_override"):
        yield
        return

    from app.main import container

    async def _predict_batch(
        *,
        model_id,
        model_uri,
        model_format,
        model_metadata,
        model_bytes,
        target,
        label_space,
        samples,
    ):
        results = []
        for s in samples:
            sid = s.get("sample_id", "")
            label = label_space[0] if label_space else "unknown"
            scores = {lbl: 1.0 / max(len(label_space), 1) for lbl in label_space}
            results.append({"sample_id": sid, "label": label, "confidence": 0.9, "scores": scores})
        return results

    async def _embed_batch(*, model_name, samples):
        results = []
        for s in samples:
            sid = s.get("sample_id", "")
            results.append({"sample_id": sid, "embedding": [0.1, 0.2, 0.3, 0.4]})
        return results

    _mock_worker = MagicMock()
    _mock_worker.predict_batch = AsyncMock(side_effect=_predict_batch)
    _mock_worker.embed_batch = AsyncMock(side_effect=_embed_batch)

    container.inference_worker.override(providers.Object(_mock_worker))
    yield
    container.inference_worker.reset_override()


# ---------------------------------------------------------------------------
# Preset registry helper
#
# After the preset refactor, presets are loaded from YAML files on disk
# (not from the database).  The registry is loaded during the FastAPI
# lifespan, but some test helpers need a known preset ID without going
# through the full app lifecycle.  This constant points to a preset that
# ships in the repo.
# ---------------------------------------------------------------------------

PRESET_ID = "resnet50-cls-v1"


# ---------------------------------------------------------------------------
# Shared test helpers
#
# Many test files define their own _create_dataset / _create_sample / _create_job
# helpers with identical patterns.  Import these from conftest when you need
# a quick dataset/sample/job and don't require special configuration.
# ---------------------------------------------------------------------------

import io as _io
import json as _json


def create_dataset(client, name="test-ds", task_spec=None):
    """Create a dataset via the API and return its ID."""
    if task_spec is None:
        task_spec = {"task_type": "classification", "label_space": ["cat", "dog"]}
    resp = client.post("/api/v1/datasets", json={"name": name, "task_spec": task_spec})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def create_sample(client, dataset_id, image_uris=None, metadata=None):
    """Create a sample in the given dataset and return its ID."""
    body: dict = {}
    if image_uris is not None:
        body["image_uris"] = image_uris
    if metadata is not None:
        body["metadata"] = metadata
    resp = client.post(f"/api/v1/datasets/{dataset_id}/samples", json=body or {})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def create_job(client, dataset_id, preset_id=None):
    """Create a training job for the given dataset and return its ID."""
    if preset_id is None:
        preset_id = PRESET_ID
    resp = client.post(
        "/api/v1/training-jobs",
        json={"dataset_id": dataset_id, "preset_id": preset_id},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def upload_model(client, job_id):
    """Upload a minimal model artifact and return its ID."""
    metadata = _json.dumps({
        "name": "test-model",
        "format": "pytorch",
        "job_id": job_id,
        "template_id": "image-classifier",
        "profile_id": "resnet50-cls-v1",
        "model_spec": {
            "framework": "pytorch",
            "architecture": "resnet50",
            "base_model": "torchvision/resnet50",
        },
        "compatibility": {
            "dataset_types": ["image_classification"],
            "task_types": ["classification"],
            "prediction_targets": ["image_classification"],
            "label_space": ["cat", "dog"],
        },
    })
    resp = client.post("/api/v1/models/upload", data={
        "metadata": metadata,
    }, files={"file": ("model.pt", _io.BytesIO(b"fake-model"), "application/octet-stream")})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]
