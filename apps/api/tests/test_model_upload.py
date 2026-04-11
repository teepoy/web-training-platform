from __future__ import annotations

import io
import json

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import PRESET_ID


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
        json={"dataset_id": dataset_id, "preset_id": PRESET_ID, "created_by": "tester"},
    )
    assert resp.status_code == 200
    return resp.json()["id"]


def test_list_model_upload_templates() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/model-upload-templates")
        assert resp.status_code == 200
        template_ids = {item["id"] for item in resp.json()}
        assert template_ids == {"image-classifier", "image-embedder", "vqa"}


def test_upload_classifier_requires_label_space() -> None:
    with TestClient(app) as c:
        job_id = _create_job(c, _create_dataset(c))
        resp = c.post(
            "/api/v1/models/upload",
            data={
                "metadata": json.dumps(
                    {
                        "name": "missing-labels",
                        "format": "pytorch",
                        "job_id": job_id,
                        "template_id": "image-classifier",
                        "profile_id": "custom",
                        "model_spec": {
                            "framework": "pytorch",
                            "architecture": "resnet18",
                            "base_model": "torchvision/resnet18",
                        },
                        "compatibility": {
                            "dataset_types": ["image_classification"],
                            "task_types": ["classification"],
                            "prediction_targets": ["image_classification"],
                            "label_space": [],
                        },
                    }
                )
            },
            files={"file": ("model.pt", io.BytesIO(b"abc"), "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "label_space" in resp.json()["detail"]


def test_upload_embedder_requires_embedding_metadata() -> None:
    with TestClient(app) as c:
        job_id = _create_job(c, _create_dataset(c))
        resp = c.post(
            "/api/v1/models/upload",
            data={
                "metadata": json.dumps(
                    {
                        "name": "embedder",
                        "format": "onnx",
                        "job_id": job_id,
                        "template_id": "image-embedder",
                        "profile_id": "custom",
                        "model_spec": {
                            "framework": "pytorch",
                            "architecture": "vit-b-16",
                            "base_model": "openai/clip-vit-base-patch32",
                        },
                        "compatibility": {
                            "dataset_types": ["image_classification"],
                            "task_types": ["classification"],
                            "prediction_targets": ["embedding"],
                            "label_space": [],
                        },
                    }
                )
            },
            files={"file": ("model.onnx", io.BytesIO(b"abc"), "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "embedding_dimension" in resp.json()["detail"]


def test_upload_vqa_rejects_label_space() -> None:
    with TestClient(app) as c:
        job_id = _create_job(c, _create_dataset(c))
        resp = c.post(
            "/api/v1/models/upload",
            data={
                "metadata": json.dumps(
                    {
                        "name": "vqa-model",
                        "format": "pytorch",
                        "job_id": job_id,
                        "template_id": "vqa",
                        "profile_id": "dspy-vqa-v1",
                        "model_spec": {
                            "framework": "dspy",
                            "architecture": "vqa-program",
                            "base_model": "gpt-4o-mini",
                        },
                        "compatibility": {
                            "dataset_types": ["image_vqa"],
                            "task_types": ["vqa"],
                            "prediction_targets": ["vqa"],
                            "label_space": ["cat"],
                        },
                    }
                )
            },
            files={"file": ("model.json", io.BytesIO(b"abc"), "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "does not allow label_space" in resp.json()["detail"]


def test_upload_classifier_persists_metadata() -> None:
    with TestClient(app) as c:
        job_id = _create_job(c, _create_dataset(c))
        resp = c.post(
            "/api/v1/models/upload",
            data={
                "metadata": json.dumps(
                    {
                        "name": "classifier",
                        "format": "pytorch",
                        "job_id": job_id,
                        "template_id": "image-classifier",
                        "profile_id": "clip-zero-shot-v1",
                        "model_spec": {
                            "framework": "pytorch",
                            "architecture": "clip-vit-base-patch32",
                            "base_model": "openai/clip-vit-base-patch32",
                        },
                        "compatibility": {
                            "dataset_types": ["image_classification"],
                            "task_types": ["classification"],
                            "prediction_targets": ["image_classification"],
                            "label_space": ["cat", "dog"],
                        },
                    }
                )
            },
            files={"file": ("model.pt", io.BytesIO(b"abc"), "application/octet-stream")},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["metadata"]["template_id"] == "image-classifier"
        assert body["metadata"]["prediction_targets"] == ["image_classification"]
        assert body["metadata"]["label_space"] == ["cat", "dog"]
