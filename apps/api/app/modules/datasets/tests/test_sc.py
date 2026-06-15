"""Tests for image_sc (patch) dataset type."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

_SC_TASK_SPEC = {
    "task_type": "sc",
    "label_space": ["defect", "clean"],
}


# ── Dataset creation ──


def test_create_sc_dataset() -> None:
    """An SC dataset can be created via the API with SC-specific view_types."""
    with TestClient(app) as c:
        resp = c.post("/api/v1/datasets", json={
            "name": "test-sc",
            "dataset_type": "image_sc",
            "task_spec": _SC_TASK_SPEC,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["dataset_type"] == "image_sc"
        assert data["task_spec"]["task_type"] == "sc"
        assert "patch_image_v1" in data["view_types"]
        assert "review_image_v1" in data["view_types"]


def test_create_sc_dataset_list_contains_it() -> None:
    """Created SC dataset appears in the list endpoint."""
    with TestClient(app) as c:
        resp = c.post("/api/v1/datasets", json={
            "name": "sc-list-test",
            "dataset_type": "image_sc",
            "task_spec": _SC_TASK_SPEC,
        })
        assert resp.status_code == 200
        dataset_id = resp.json()["id"]
        resp2 = c.get("/api/v1/datasets")
        assert resp2.status_code == 200
        ids = [d["id"] for d in resp2.json()]
        assert dataset_id in ids


def test_create_sc_dataset_wrong_task_type_rejected() -> None:
    """SC dataset with classification task_type is rejected."""
    with TestClient(app) as c:
        resp = c.post("/api/v1/datasets", json={
            "name": "bad-sc",
            "dataset_type": "image_sc",
            "task_spec": {"task_type": "classification", "label_space": ["cat"]},
        })
        assert resp.status_code == 422


# ── Sample upload ──


def test_upload_sc_sample_with_metadata() -> None:
    """Samples with SC-specific metadata can be uploaded."""
    with TestClient(app) as c:
        resp = c.post("/api/v1/datasets", json={
            "name": "sc-sample-test",
            "dataset_type": "image_sc",
            "task_spec": _SC_TASK_SPEC,
        })
        assert resp.status_code == 200
        dataset_id = resp.json()["id"]

        resp2 = c.post(f"/api/v1/datasets/{dataset_id}/samples", json={
            "image_uris": ["http://x.com/t.png", "http://x.com/d.png", "http://x.com/diff.png"],
            "metadata": {
                "inspection_time": "2024-01-01T00:00:00Z",
                "wafer_key": 1,
                "defect_id": "D001",
                "wafer_x": 100,
                "wafer_y": 200,
                "rough_bin": 0,
                "class_number": 1,
                "patch_images": {"defective": {"image_url": "http://x.com/d.png", "image_name": "d.png"}},
                "review_images": [],
            },
        })
        assert resp2.status_code == 200


def test_list_sc_samples_preserves_metadata() -> None:
    """SC sample metadata round-trips correctly."""
    with TestClient(app) as c:
        resp = c.post("/api/v1/datasets", json={
            "name": "sc-roundtrip",
            "dataset_type": "image_sc",
            "task_spec": _SC_TASK_SPEC,
        })
        assert resp.status_code == 200
        dataset_id = resp.json()["id"]

        c.post(f"/api/v1/datasets/{dataset_id}/samples", json={
            "image_uris": ["http://x.com/t.png", "http://x.com/d.png", "http://x.com/diff.png"],
            "metadata": {"wafer_key": 1, "defect_id": "D001", "wafer_x": 100, "wafer_y": 200, "rough_bin": 5, "class_number": 3},
        })

        resp3 = c.get(f"/api/v1/datasets/{dataset_id}/samples")
        assert resp3.status_code == 200
        data = resp3.json()
        items = data["items"]
        assert len(items) >= 1
        meta = items[0]["metadata"]
        assert meta["wafer_key"] == 1
        assert meta["rough_bin"] == 5
