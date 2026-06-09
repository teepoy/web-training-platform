from __future__ import annotations

import io as _io
import json as _json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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

DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000002"


# auth + ls_client mocks moved to root conftest.py — available globally for
# app/modules/*/tests/ without pytest_plugins double-registration.


# ---------------------------------------------------------------------------
# Trainer registry helper
#
# Known trainer IDs used by test helpers that need a valid trainer ID
# without going through the full app lifecycle.
# ---------------------------------------------------------------------------

TRAINER_ID = "resnet50-sc-v1"
VIEW_ID = "labeled_image_v1"


# ---------------------------------------------------------------------------
# Shared test helpers
#
# Many test files define their own _create_dataset / _create_sample / _create_job
# helpers with identical patterns.  Import these from conftest when you need
# a quick dataset/sample/job and don't require special configuration.
# ---------------------------------------------------------------------------


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


def create_job(client, dataset_id, trainer_id=None):
    """Create a training job for the given dataset and return its ID."""
    if trainer_id is None:
        trainer_id = TRAINER_ID
    resp = client.post(
        "/api/v1/training-jobs",
        json={"dataset_id": dataset_id, "trainer_id": trainer_id},
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
        "profile_id": "resnet50-sc-v1",
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
