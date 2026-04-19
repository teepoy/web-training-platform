"""Route-level tests for dataset endpoints.

Covers:
- PATCH /datasets/{id}/public
- GET   /datasets/{id}/embed-config
- PATCH /datasets/{id}/embed-config
- POST  /datasets/{id}/annotations/bulk
- GET   /datasets/{id}/similarity/{sample_id}
- GET   /datasets/{id}/selection-metrics
- GET   /datasets/{id}/hints/uncovered
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app, container

_TASK_SPEC = {"task_type": "classification", "label_space": ["cat", "dog"]}


def _create_dataset(c: TestClient) -> str:
    resp = c.post("/api/v1/datasets", json={
        "name": "ds-route-test",
        "dataset_type": "image_classification",
        "task_spec": _TASK_SPEC,
    })
    assert resp.status_code == 200
    return resp.json()["id"]


def _create_sample(c: TestClient, dataset_id: str) -> str:
    resp = c.post(f"/api/v1/datasets/{dataset_id}/samples", json={
        "image_uris": [],
        "metadata": {},
    })
    assert resp.status_code == 200
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Set dataset public
# ---------------------------------------------------------------------------

def test_set_dataset_public() -> None:
    with TestClient(app) as c:
        dataset_id = _create_dataset(c)
        resp = c.patch(f"/api/v1/datasets/{dataset_id}/public", json={"is_public": True})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


def test_set_dataset_public_not_found() -> None:
    with TestClient(app) as c:
        resp = c.patch("/api/v1/datasets/nonexistent/public", json={"is_public": True})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Embed config
# ---------------------------------------------------------------------------

def test_get_embed_config_default() -> None:
    with TestClient(app) as c:
        dataset_id = _create_dataset(c)
        resp = c.get(f"/api/v1/datasets/{dataset_id}/embed-config")
        assert resp.status_code == 200
        # Default is empty dict or whatever the dataset was created with
        assert isinstance(resp.json(), dict)


def test_get_embed_config_not_found() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/datasets/nonexistent/embed-config")
        assert resp.status_code == 404


def test_update_embed_config() -> None:
    with TestClient(app) as c:
        dataset_id = _create_dataset(c)
        resp = c.patch(f"/api/v1/datasets/{dataset_id}/embed-config", json={
            "model": "clip-vit-b32",
            "dimension": 768,
        })
        assert resp.status_code == 200
        assert resp.json()["model"] == "clip-vit-b32"
        assert resp.json()["dimension"] == 768

        # Verify it persisted
        get_resp = c.get(f"/api/v1/datasets/{dataset_id}/embed-config")
        assert get_resp.status_code == 200
        assert get_resp.json()["model"] == "clip-vit-b32"


def test_update_embed_config_not_found() -> None:
    with TestClient(app) as c:
        resp = c.patch("/api/v1/datasets/nonexistent/embed-config", json={
            "model": "clip",
            "dimension": 512,
        })
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Bulk annotations
# ---------------------------------------------------------------------------

def test_bulk_create_annotations() -> None:
    with TestClient(app) as c:
        dataset_id = _create_dataset(c)
        s1 = _create_sample(c, dataset_id)
        s2 = _create_sample(c, dataset_id)

        resp = c.post(f"/api/v1/datasets/{dataset_id}/annotations/bulk", json={
            "annotations": [
                {"sample_id": s1, "label": "cat"},
                {"sample_id": s2, "label": "dog"},
            ],
        })
        assert resp.status_code == 200
        assert resp.json()["created"] == 2


def test_bulk_create_annotations_dataset_not_found() -> None:
    with TestClient(app) as c:
        resp = c.post("/api/v1/datasets/nonexistent/annotations/bulk", json={
            "annotations": [{"sample_id": "x", "label": "cat"}],
        })
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Similarity search (requires feature_ops mock)
# ---------------------------------------------------------------------------

def test_similarity_search() -> None:
    with TestClient(app) as c:
        dataset_id = _create_dataset(c)
        sample_id = _create_sample(c, dataset_id)

        mock_result = {"neighbors": [], "query_sample_id": sample_id}
        with patch.object(
            container.feature_ops(), "similarity_search",
            new_callable=AsyncMock, return_value=mock_result,
        ):
            resp = c.get(f"/api/v1/datasets/{dataset_id}/similarity/{sample_id}")
        assert resp.status_code == 200
        assert resp.json()["query_sample_id"] == sample_id


def test_similarity_search_dataset_not_found() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/datasets/nonexistent/similarity/some-sample")
        assert resp.status_code == 404


def test_similarity_search_sample_not_found() -> None:
    with TestClient(app) as c:
        dataset_id = _create_dataset(c)
        resp = c.get(f"/api/v1/datasets/{dataset_id}/similarity/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Selection metrics (requires feature_ops mock)
# ---------------------------------------------------------------------------

def test_selection_metrics() -> None:
    with TestClient(app) as c:
        dataset_id = _create_dataset(c)
        _create_sample(c, dataset_id)

        mock_uniqueness = AsyncMock(return_value={"scores": {}})
        mock_repr = AsyncMock(return_value={"scores": {}})
        fs = container.feature_ops()
        with patch.object(fs, "uniqueness_scores", mock_uniqueness), \
             patch.object(fs, "representativeness_scores", mock_repr):
            resp = c.get(f"/api/v1/datasets/{dataset_id}/selection-metrics")
        assert resp.status_code == 200
        body = resp.json()
        assert "uniqueness" in body
        assert "representativeness" in body


def test_selection_metrics_dataset_not_found() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/datasets/nonexistent/selection-metrics")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Uncovered hints (requires feature_ops mock)
# ---------------------------------------------------------------------------

def test_uncovered_hints() -> None:
    with TestClient(app) as c:
        dataset_id = _create_dataset(c)

        mock_result = {"clusters": [], "uncovered": []}
        with patch.object(
            container.feature_ops(), "uncovered_cluster_hints",
            new_callable=AsyncMock, return_value=mock_result,
        ):
            resp = c.get(f"/api/v1/datasets/{dataset_id}/hints/uncovered")
        assert resp.status_code == 200


def test_uncovered_hints_dataset_not_found() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/datasets/nonexistent/hints/uncovered")
        assert resp.status_code == 404
