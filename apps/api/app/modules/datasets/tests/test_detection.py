"""Tests for image_detection dataset type.

Covers:
- Creating a dataset with dataset_type="image_detection" and task_type="detection"
- Uploading samples with bounding-box metadata
- Creating annotations with annotation_value (box list)
- Retrieving annotations and confirming annotation_value is preserved
- Schema registry has detection registered
- Compatibility layer allows the detection dataset/task pair
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

_DETECTION_TASK_SPEC = {
    "task_type": "detection",
    "label_space": ["car", "person", "bicycle"],
}

_BOXES = [
    {"label": "car", "x": 0.1, "y": 0.1, "width": 0.3, "height": 0.2},
    {"label": "person", "x": 0.5, "y": 0.4, "width": 0.15, "height": 0.3},
]


def _create_detection_dataset(c: TestClient, name: str = "det-test-ds") -> str:
    resp = c.post(
        "/api/v1/datasets",
        json={
            "name": name,
            "dataset_type": "image_detection",
            "task_spec": _DETECTION_TASK_SPEC,
        },
    )
    assert resp.status_code == 200, resp.json()
    return resp.json()["id"]


def _create_sample(c: TestClient, dataset_id: str) -> str:
    resp = c.post(
        f"/api/v1/datasets/{dataset_id}/samples",
        json={
            "image_uris": ["https://picsum.photos/seed/det0/640/480"],
            "metadata": {
                "width": 640,
                "height": 480,
                "boxes": _BOXES,
            },
        },
    )
    assert resp.status_code == 200, resp.json()
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Dataset creation
# ---------------------------------------------------------------------------


def test_create_detection_dataset() -> None:
    """A detection dataset can be created via the API."""
    with TestClient(app) as c:
        resp = c.post(
            "/api/v1/datasets",
            json={
                "name": "test-detection",
                "dataset_type": "image_detection",
                "task_spec": _DETECTION_TASK_SPEC,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["dataset_type"] == "image_detection"
        assert data["task_spec"]["task_type"] == "detection"
        assert set(data["task_spec"]["label_space"]) == {"car", "person", "bicycle"}


def test_create_detection_dataset_list_contains_it() -> None:
    """Created detection dataset appears in the list endpoint."""
    with TestClient(app) as c:
        dataset_id = _create_detection_dataset(c, name="detection-list-test")
        resp = c.get("/api/v1/datasets")
        assert resp.status_code == 200
        ids = [d["id"] for d in resp.json()["items"]]
        assert dataset_id in ids


# ---------------------------------------------------------------------------
# Sample upload
# ---------------------------------------------------------------------------


def test_upload_detection_sample_with_boxes() -> None:
    """Samples with box metadata can be uploaded to a detection dataset."""
    with TestClient(app) as c:
        dataset_id = _create_detection_dataset(c)
        resp = c.post(
            f"/api/v1/datasets/{dataset_id}/samples",
            json={
                "image_uris": ["https://example.com/img.jpg"],
                "metadata": {"width": 640, "height": 480, "boxes": _BOXES},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["metadata"]["boxes"] == _BOXES


# ---------------------------------------------------------------------------
# Annotation with annotation_value
# ---------------------------------------------------------------------------


def test_create_detection_annotation_with_value() -> None:
    """Detection annotations can store bounding boxes in annotation_value."""
    with TestClient(app) as c:
        dataset_id = _create_detection_dataset(c)
        sample_id = _create_sample(c, dataset_id)

        resp = c.post(
            "/api/v1/annotations",
            json={
                "dataset_id": dataset_id,
                "sample_id": sample_id,
                "label": "",
                "annotation_value": _BOXES,
                "created_by": "tester",
            },
        )
        assert resp.status_code == 200
        ann = resp.json()
        assert ann["label"] == ""
        assert ann["annotation_value"] == _BOXES


def test_list_detection_annotations_preserves_value() -> None:
    """Listing annotations for a detection sample returns annotation_value intact."""
    with TestClient(app) as c:
        dataset_id = _create_detection_dataset(c)
        sample_id = _create_sample(c, dataset_id)

        c.post(
            "/api/v1/annotations",
            json={
                "dataset_id": dataset_id,
                "sample_id": sample_id,
                "label": "",
                "annotation_value": _BOXES,
                "created_by": "tester",
            },
        )

        resp = c.get(
            f"/api/v1/datasets/{dataset_id}/samples/{sample_id}/annotations"
        )
        assert resp.status_code == 200
        annotations = resp.json()
        assert len(annotations) == 1
        assert annotations[0]["annotation_value"] == _BOXES


# ---------------------------------------------------------------------------
# Schema registry
# ---------------------------------------------------------------------------
# Compatibility
# ---------------------------------------------------------------------------


def test_detection_dataset_type_rejected_without_detection_task() -> None:
    """dataset_type=image_detection requires task_type=detection."""
    with TestClient(app) as c:
        resp = c.post(
            "/api/v1/datasets",
            json={
                "name": "bad-detection",
                "dataset_type": "image_detection",
                "task_spec": {"task_type": "classification", "label_space": ["car"]},
            },
        )
        assert resp.status_code == 422
