from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app, container
from app.domain.types import DatasetStorageMode


_TASK_SPEC = {"task_type": "classification", "label_space": ["cat", "dog"]}


# ---------------------------------------------------------------------------
# Create sparse dataset
# ---------------------------------------------------------------------------


def test_create_sparse_dataset() -> None:
    with TestClient(app) as c:
        resp = c.post("/api/v1/datasets", json={
            "name": "sparse-create-test",
            "dataset_type": "image_classification",
            "task_spec": _TASK_SPEC,
            "storage_mode": "file_shard_sparse",
        })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["name"] == "sparse-create-test"
        assert body["storage_mode"] == DatasetStorageMode.FILE_SHARD_SPARSE.value
        assert body.get("ls_project_id") == "SPARSE_NO_LS"
        assert body.get("ls_project_url") is None


# ---------------------------------------------------------------------------
# Capability gating — sparse datasets reject operations that need samples
# ---------------------------------------------------------------------------


def test_sparse_dataset_rejects_samples() -> None:
    with TestClient(app) as c:
        ds = c.post("/api/v1/datasets", json={
            "name": "sparse-reject-samples",
            "dataset_type": "image_classification",
            "task_spec": _TASK_SPEC,
            "storage_mode": "file_shard_sparse",
        })
        assert ds.status_code == 200
        ds_id = ds.json()["id"]

        resp = c.post(f"/api/v1/datasets/{ds_id}/samples", json={
            "image_uris": [],
            "metadata": {},
        })
        assert resp.status_code == 409
        assert "not supported" in resp.json()["detail"]


def test_sparse_dataset_rejects_annotations() -> None:
    with TestClient(app) as c:
        ds = c.post("/api/v1/datasets", json={
            "name": "sparse-reject-annotations",
            "dataset_type": "image_classification",
            "task_spec": _TASK_SPEC,
            "storage_mode": "file_shard_sparse",
        })
        assert ds.status_code == 200
        ds_id = ds.json()["id"]

        resp = c.post(f"/api/v1/datasets/{ds_id}/annotations/bulk", json={
            "annotations": [{"sample_id": "nonexistent", "label": "cat"}],
        })
        assert resp.status_code == 409
        assert "not supported" in resp.json()["detail"]


def test_sparse_dataset_rejects_sync_to_ls() -> None:
    with TestClient(app) as c:
        ds = c.post("/api/v1/datasets", json={
            "name": "sparse-reject-sync",
            "dataset_type": "image_classification",
            "task_spec": _TASK_SPEC,
            "storage_mode": "file_shard_sparse",
        })
        assert ds.status_code == 200
        ds_id = ds.json()["id"]

        resp = c.post(f"/api/v1/datasets/{ds_id}/sync-annotations-to-ls")
        assert resp.status_code == 409
        assert "not supported" in resp.json()["detail"]


def test_sparse_dataset_rejects_export() -> None:
    with TestClient(app) as c:
        ds = c.post("/api/v1/datasets", json={
            "name": "sparse-reject-export",
            "dataset_type": "image_classification",
            "task_spec": _TASK_SPEC,
            "storage_mode": "file_shard_sparse",
        })
        assert ds.status_code == 200
        ds_id = ds.json()["id"]

        resp = c.get(f"/api/v1/exports/{ds_id}")
        assert resp.status_code == 409
        assert "not supported" in resp.json()["detail"]


def test_sparse_dataset_rejects_training() -> None:
    with TestClient(app) as c:
        ds = c.post("/api/v1/datasets", json={
            "name": "sparse-reject-training",
            "dataset_type": "image_classification",
            "task_spec": _TASK_SPEC,
            "storage_mode": "file_shard_sparse",
        })
        assert ds.status_code == 200
        ds_id = ds.json()["id"]

        resp = c.post("/api/v1/training-jobs", json={
            "dataset_id": ds_id,
            "preset_id": "resnet50-cls-v1",
            "created_by": "tester",
        })
        assert resp.status_code == 409
        assert "not supported" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Regression — normal ``db_full`` datasets still work
# ---------------------------------------------------------------------------


def test_db_full_dataset_accepts_samples() -> None:
    with TestClient(app) as c:
        resp = c.post("/api/v1/datasets", json={
            "name": "normal-ds",
            "dataset_type": "image_classification",
            "task_spec": _TASK_SPEC,
            "storage_mode": "db_full",
        })
        assert resp.status_code == 200
        ds_id = resp.json()["id"]

        sample_resp = c.post(f"/api/v1/datasets/{ds_id}/samples", json={
            "image_uris": [],
            "metadata": {},
        })
        assert sample_resp.status_code == 200, sample_resp.text


# ---------------------------------------------------------------------------
# Sparse summary endpoint
# ---------------------------------------------------------------------------


def test_sparse_summary_endpoint_returns_empty_manifest() -> None:
    with TestClient(app) as c:
        ds = c.post("/api/v1/datasets", json={
            "name": "sparse-summary-test",
            "dataset_type": "image_classification",
            "task_spec": _TASK_SPEC,
            "storage_mode": "file_shard_sparse",
        })
        assert ds.status_code == 200
        ds_id = ds.json()["id"]

        resp = c.get(f"/api/v1/datasets/{ds_id}/sparse-summary")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["dataset_id"] == ds_id
        assert body["storage_mode"] == "file_shard_sparse"
        assert body["manifest"]["shard_count"] == 0
        assert body["manifest"]["total_rows"] == 0
        assert body["shards"] == []
        assert body["sample_rows"] == []


def test_sparse_summary_rejects_db_full_dataset() -> None:
    with TestClient(app) as c:
        ds = c.post("/api/v1/datasets", json={
            "name": "db-full-summary-test",
            "dataset_type": "image_classification",
            "task_spec": _TASK_SPEC,
            "storage_mode": "db_full",
        })
        assert ds.status_code == 200
        ds_id = ds.json()["id"]

        resp = c.get(f"/api/v1/datasets/{ds_id}/sparse-summary")
        assert resp.status_code == 409
        assert "file_shard_sparse datasets only" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Delete lifecycle — sparse datasets skip LS deletion
# ---------------------------------------------------------------------------


def test_sparse_delete_lifecycle() -> None:
    with TestClient(app) as c:
        ds = c.post("/api/v1/datasets", json={
            "name": "sparse-delete-test",
            "dataset_type": "image_classification",
            "task_spec": _TASK_SPEC,
            "storage_mode": "file_shard_sparse",
        })
        assert ds.status_code == 200
        ds_id = ds.json()["id"]

        ls_mock = container.label_studio_client()
        ls_mock.delete_project.reset_mock()

        deleted = c.delete(f"/api/v1/datasets/{ds_id}")
        assert deleted.status_code == 204

        get_resp = c.get(f"/api/v1/datasets/{ds_id}")
        assert get_resp.status_code == 404

        ls_mock.delete_project.assert_not_called()
