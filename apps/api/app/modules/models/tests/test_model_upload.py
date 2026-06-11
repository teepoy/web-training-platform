from __future__ import annotations

import io
import json

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import TRAINER_ID


def _create_dataset(c: TestClient) -> str:
    resp = c.post(
        "/api/v1/datasets",
        json={
            "name": "upload-ds",
            "dataset_type": "image_classification",
            "task_spec": {"task_type": "classification", "label_space": ["cat", "dog", "bird"]},
        },
    )
    assert resp.status_code == 200
    return resp.json()["id"]


def _create_job(c: TestClient, dataset_id: str) -> str:
    resp = c.post(
        "/api/v1/training-jobs",
        json={"dataset_id": dataset_id, "trainer_id": TRAINER_ID, "created_by": "tester"},
    )
    assert resp.status_code == 200
    return resp.json()["id"]


def test_list_model_upload_templates() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/model-upload-templates")
        assert resp.status_code == 200
        template_ids = {item["id"] for item in resp.json()}
        assert template_ids == {"image-classifier", "image-embedder", "vqa"}
