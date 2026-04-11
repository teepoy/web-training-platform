import io

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import PRESET_ID


def test_dataset_and_job_flow() -> None:
    with TestClient(app) as c:
        ds = c.post("/api/v1/datasets", json={"name": "d1", "dataset_type": "image_classification", "task_spec": {"task_type": "classification", "label_space": ["a", "b"]}})
        assert ds.status_code == 200
        dataset_id = ds.json()["id"]

        job = c.post("/api/v1/training-jobs", json={"dataset_id": dataset_id, "preset_id": PRESET_ID, "created_by": "u1"})
        assert job.status_code == 200
        job_id = job.json()["id"]

        r = c.get(f"/api/v1/training-jobs/{job_id}")
        assert r.status_code == 200


def test_get_dataset_detail() -> None:
    with TestClient(app) as c:
        created = c.post(
            "/api/v1/datasets",
            json={"name": "detail-ds", "dataset_type": "image_classification", "task_spec": {"task_type": "classification", "label_space": ["x", "y"]}},
        )
        assert created.status_code == 200
        dataset_id = created.json()["id"]

        r = c.get(f"/api/v1/datasets/{dataset_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == dataset_id
        assert body["name"] == "detail-ds"
        assert body["task_spec"]["label_space"] == ["x", "y"]


def test_get_dataset_detail_not_found() -> None:
    with TestClient(app) as c:
        r = c.get("/api/v1/datasets/nonexistent-id-12345")
        assert r.status_code == 404
        assert r.json()["detail"] == "Dataset not found"


def test_update_label_space() -> None:
    with TestClient(app) as c:
        # Create dataset with initial labels
        created = c.post(
            "/api/v1/datasets",
            json={"name": "label-update-ds", "dataset_type": "image_classification", "task_spec": {"task_type": "classification", "label_space": ["cat", "dog"]}},
        )
        assert created.status_code == 200
        dataset_id = created.json()["id"]
        assert created.json()["task_spec"]["label_space"] == ["cat", "dog"]

        # Add a new label
        r = c.patch(
            f"/api/v1/datasets/{dataset_id}/label-space",
            json={"label_space": ["cat", "dog", "bird"]},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["task_spec"]["label_space"] == ["cat", "dog", "bird"]

        # Verify the change persisted
        r = c.get(f"/api/v1/datasets/{dataset_id}")
        assert r.status_code == 200
        assert r.json()["task_spec"]["label_space"] == ["cat", "dog", "bird"]


def test_update_label_space_not_found() -> None:
    with TestClient(app) as c:
        r = c.patch(
            "/api/v1/datasets/nonexistent-id-12345/label-space",
            json={"label_space": ["a", "b"]},
        )
        assert r.status_code == 404


def test_get_preset_detail() -> None:
    with TestClient(app) as c:
        r = c.get(f"/api/v1/training-presets/{PRESET_ID}")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == PRESET_ID
        assert body["name"] == "ResNet50 Classification (v1)"
        assert body["trainable"] is True
        assert body["model_spec"]["base_model"] == "torchvision/resnet50"


def test_get_inference_only_preset_detail() -> None:
    with TestClient(app) as c:
        r = c.get("/api/v1/training-presets/clip-zero-shot-v1")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == "clip-zero-shot-v1"
        assert body["trainable"] is False


def test_get_preset_detail_not_found() -> None:
    with TestClient(app) as c:
        r = c.get("/api/v1/training-presets/nonexistent-id-12345")
        assert r.status_code == 404
        assert r.json()["detail"] == "Preset not found"


def test_samples_pagination() -> None:
    with TestClient(app) as c:
        # Create a dataset
        ds = c.post(
            "/api/v1/datasets",
            json={"name": "paginate-ds", "dataset_type": "image_classification", "task_spec": {"task_type": "classification", "label_space": ["a", "b"]}},
        )
        assert ds.status_code == 200
        dataset_id = ds.json()["id"]

        # Create 3 samples
        for i in range(3):
            r = c.post(f"/api/v1/datasets/{dataset_id}/samples", json={"image_uris": [f"s3://bucket/img{i}.jpg"]})
            assert r.status_code == 200

        # limit=2, offset=0 → 2 items, total=3
        r = c.get(f"/api/v1/datasets/{dataset_id}/samples?offset=0&limit=2")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 3
        assert len(body["items"]) == 2

        # offset=2, limit=50 → 1 item, total=3
        r = c.get(f"/api/v1/datasets/{dataset_id}/samples?offset=2&limit=50")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 3
        assert len(body["items"]) == 1

        # default params → all 3 items, total=3
        r = c.get(f"/api/v1/datasets/{dataset_id}/samples")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 3
        assert len(body["items"]) == 3


def test_events_history_pagination() -> None:
    with TestClient(app) as c:
        # Set up dataset + job
        ds = c.post(
            "/api/v1/datasets",
            json={"name": "event-ds", "dataset_type": "image_classification", "task_spec": {"task_type": "classification", "label_space": ["a", "b"]}},
        )
        assert ds.status_code == 200
        dataset_id = ds.json()["id"]

        job = c.post(
            "/api/v1/training-jobs",
            json={"dataset_id": dataset_id, "preset_id": PRESET_ID, "created_by": "tester"},
        )
        assert job.status_code == 200
        job_id = job.json()["id"]

        # History endpoint returns paginated response (may have events from orchestrator startup)
        r = c.get(f"/api/v1/training-jobs/{job_id}/events/history")
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        assert "total" in body
        assert isinstance(body["items"], list)
        assert isinstance(body["total"], int)
        assert body["total"] == len(body["items"])  # default limit=50 fetches all for a new job

        # Query with explicit offset/limit
        r = c.get(f"/api/v1/training-jobs/{job_id}/events/history?offset=0&limit=2")
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        assert "total" in body
        assert len(body["items"]) <= 2

        # 404 for unknown job
        r = c.get("/api/v1/training-jobs/nonexistent-job-xyz/events/history")
        assert r.status_code == 404


def test_create_training_job_rejects_inference_only_preset() -> None:
    with TestClient(app) as c:
        ds = c.post(
            "/api/v1/datasets",
            json={"name": "clip-ds", "dataset_type": "image_classification", "task_spec": {"task_type": "classification", "label_space": ["cat", "dog"]}},
        )
        assert ds.status_code == 200
        dataset_id = ds.json()["id"]

        r = c.post(
            "/api/v1/training-jobs",
            json={"dataset_id": dataset_id, "preset_id": "clip-zero-shot-v1", "created_by": "tester"},
        )
        assert r.status_code == 422
        assert "inference-only" in r.json()["detail"]


def test_extract_features_runs_sync() -> None:
    with TestClient(app) as c:
        data_uri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/4gkAAAAASUVORK5CYII="
        ds = c.post(
            "/api/v1/datasets",
            json={"name": "feature-ds", "dataset_type": "image_classification", "task_spec": {"task_type": "classification", "label_space": ["cat"]}},
        )
        assert ds.status_code == 200
        dataset_id = ds.json()["id"]
        s = c.post(
            f"/api/v1/datasets/{dataset_id}/samples",
            json={"image_uris": [data_uri]},
        )
        assert s.status_code == 200

        r = c.post(f"/api/v1/datasets/{dataset_id}/features/extract")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "completed"
        assert body["target"] == "embedding"
        assert "summary" in body
        assert "processed" in body["summary"]


def test_create_prediction_job_async() -> None:
    with TestClient(app) as c:
        ds = c.post(
            "/api/v1/datasets",
            json={"name": "pred-ds", "dataset_type": "image_classification", "task_spec": {"task_type": "classification", "label_space": ["a", "b"]}},
        )
        assert ds.status_code == 200
        dataset_id = ds.json()["id"]

        job = c.post(
            "/api/v1/training-jobs",
            json={"dataset_id": dataset_id, "preset_id": PRESET_ID, "created_by": "u1"},
        )
        assert job.status_code == 200
        job_id = job.json()["id"]

        upload = c.post(
            "/api/v1/models/upload",
            files={"file": ("model.json", io.BytesIO(b'{"label_prototypes":{"a":[1.0],"b":[0.0]}}'), "application/json")},
            data={
                "metadata": '{"name":"uploaded-model","job_id":"' + job_id + '","template_id":"image-classifier","profile_id":"resnet50-cls-v1","format":"pytorch","model_spec":{"framework":"pytorch","architecture":"resnet50","base_model":"torchvision/resnet50"},"compatibility":{"dataset_types":["image_classification"],"task_types":["classification"],"prediction_targets":["image_classification"],"label_space":["a","b"]}}',
            },
        )
        assert upload.status_code == 200
        model_id = upload.json()["id"]

        r = c.post(
            "/api/v1/predictions/run",
            json={"model_id": model_id, "dataset_id": dataset_id, "target": "image_classification"},
        )
        assert r.status_code == 202
        body = r.json()
        assert body["model_id"] == model_id
        assert body["dataset_id"] == dataset_id
        assert body["status"] in {"running", "queued", "completed"}

        listing = c.get("/api/v1/prediction-jobs")
        assert listing.status_code == 200
        assert any(item["id"] == body["id"] for item in listing.json())


@pytest.mark.no_auth_override
def test_auth_me_requires_auth() -> None:
    with TestClient(app) as c:
        r = c.get("/api/v1/auth/me")
        assert r.status_code == 401


def test_create_dataset_rejects_incompatible_dataset_and_task() -> None:
    with TestClient(app) as c:
        r = c.post(
            "/api/v1/datasets",
            json={
                "name": "bad-vqa-ds",
                "dataset_type": "image_vqa",
                "task_spec": {"task_type": "classification", "label_space": ["cat"]},
            },
        )
        assert r.status_code == 422
        assert "incompatible" in r.json()["detail"]


def test_create_vqa_dataset_requires_empty_label_space() -> None:
    with TestClient(app) as c:
        r = c.post(
            "/api/v1/datasets",
            json={
                "name": "vqa-ds",
                "dataset_type": "image_vqa",
                "task_spec": {"task_type": "vqa", "label_space": ["nope"]},
            },
        )
        assert r.status_code == 422
        assert "must not define a label space" in r.json()["detail"]


def test_create_training_job_rejects_incompatible_dataset_and_preset() -> None:
    with TestClient(app) as c:
        ds = c.post(
            "/api/v1/datasets",
            json={"name": "vqa-train", "dataset_type": "image_vqa", "task_spec": {"task_type": "vqa", "label_space": []}},
        )
        assert ds.status_code == 200
        r = c.post(
            "/api/v1/training-jobs",
            json={"dataset_id": ds.json()["id"], "preset_id": PRESET_ID, "created_by": "tester"},
        )
        assert r.status_code == 422
        assert "does not support dataset_type" in r.json()["detail"]


def test_auth_callback_removed() -> None:
    with TestClient(app) as c:
        r = c.post("/api/v1/auth/callback")
        assert r.status_code == 404
