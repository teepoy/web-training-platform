"""Tests for GET /api/v1/datasets/{dataset_id}/samples-with-labels endpoint.

TDD: These tests are written before implementation and MUST fail initially.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TASK_SPEC = {"task_type": "classification", "label_space": ["cat", "dog"]}


def _create_dataset(c: TestClient, name: str = "classify-test-ds") -> str:
    """Create a dataset and return dataset_id."""
    ds = c.post(
        "/api/v1/datasets",
        json={"name": name, "task_spec": _TASK_SPEC},
    )
    assert ds.status_code == 200
    return ds.json()["id"]


def _create_sample(c: TestClient, dataset_id: str, image_uris: list[str] | None = None) -> str:
    """Create a sample and return sample_id."""
    sample = c.post(
        f"/api/v1/datasets/{dataset_id}/samples",
        json={"image_uris": image_uris or []},
    )
    assert sample.status_code == 200
    return sample.json()["id"]


def _create_annotation(c: TestClient, sample_id: str, label: str, created_by: str = "tester") -> str:
    """Create an annotation and return annotation_id."""
    r = c.post(
        "/api/v1/annotations",
        json={"sample_id": sample_id, "label": label, "created_by": created_by},
    )
    assert r.status_code == 200
    return r.json()["id"]


# ---------------------------------------------------------------------------
# Test 1: Happy path — enriched response shape with annotations
# ---------------------------------------------------------------------------


def test_samples_with_labels_happy_path() -> None:
    """Create dataset + 3 samples + annotations for 2 → correct enriched shape."""
    with TestClient(app) as c:
        dataset_id = _create_dataset(c)

        # 3 samples
        s1 = _create_sample(c, dataset_id)
        s2 = _create_sample(c, dataset_id)
        s3 = _create_sample(c, dataset_id)

        # annotations for s1 and s2 (s3 unannotated)
        _create_annotation(c, s1, "cat")
        _create_annotation(c, s2, "dog")

        resp = c.get(f"/api/v1/datasets/{dataset_id}/samples-with-labels")
        assert resp.status_code == 200

        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert body["total"] == 3
        assert len(body["items"]) == 3

        # Find s1 in items
        s1_item = next(item for item in body["items"] if item["id"] == s1)

        # Check required fields exist
        assert "id" in s1_item
        assert "dataset_id" in s1_item
        assert s1_item["dataset_id"] == dataset_id
        assert "image_uris" in s1_item
        assert "metadata" in s1_item
        assert "latest_annotation" in s1_item

        # s1 has annotation
        assert s1_item["latest_annotation"] is not None
        assert s1_item["latest_annotation"]["label"] == "cat"
        assert "id" in s1_item["latest_annotation"]
        assert "created_by" in s1_item["latest_annotation"]
        assert "created_at" in s1_item["latest_annotation"]

        # s3 has no annotation
        s3_item = next(item for item in body["items"] if item["id"] == s3)
        assert s3_item["latest_annotation"] is None


# ---------------------------------------------------------------------------
# Test 2: Pagination — offset + limit
# ---------------------------------------------------------------------------


def test_samples_with_labels_pagination() -> None:
    """5 samples → ?offset=0&limit=2 → items length == 2, total == 5."""
    with TestClient(app) as c:
        dataset_id = _create_dataset(c, name="paginate-test-ds")

        for _ in range(5):
            _create_sample(c, dataset_id)

        resp = c.get(f"/api/v1/datasets/{dataset_id}/samples-with-labels?offset=0&limit=2")
        assert resp.status_code == 200

        body = resp.json()
        assert body["total"] == 5
        assert len(body["items"]) == 2

        # Second page
        resp2 = c.get(f"/api/v1/datasets/{dataset_id}/samples-with-labels?offset=2&limit=2")
        assert resp2.status_code == 200
        body2 = resp2.json()
        assert body2["total"] == 5
        assert len(body2["items"]) == 2


# ---------------------------------------------------------------------------
# Test 3: Label filter — by annotation label and __unlabeled__
# ---------------------------------------------------------------------------


def test_samples_with_labels_label_filter() -> None:
    """3 samples annotated cat/dog/unlabeled → ?label=cat → 1; ?label=__unlabeled__ → 1."""
    with TestClient(app) as c:
        dataset_id = _create_dataset(c, name="filter-test-ds")

        s1 = _create_sample(c, dataset_id)
        s2 = _create_sample(c, dataset_id)
        s3 = _create_sample(c, dataset_id)

        _create_annotation(c, s1, "cat")
        _create_annotation(c, s2, "dog")
        # s3 remains unlabeled

        # Filter by "cat"
        resp = c.get(f"/api/v1/datasets/{dataset_id}/samples-with-labels?label=cat")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["latest_annotation"]["label"] == "cat"

        # Filter by "dog"
        resp2 = c.get(f"/api/v1/datasets/{dataset_id}/samples-with-labels?label=dog")
        assert resp2.status_code == 200
        assert resp2.json()["total"] == 1

        # Filter by __unlabeled__
        resp3 = c.get(f"/api/v1/datasets/{dataset_id}/samples-with-labels?label=__unlabeled__")
        assert resp3.status_code == 200
        body3 = resp3.json()
        assert body3["total"] == 1
        assert len(body3["items"]) == 1
        assert body3["items"][0]["latest_annotation"] is None


# ---------------------------------------------------------------------------
# Test 4: Empty dataset
# ---------------------------------------------------------------------------


def test_samples_with_labels_empty_dataset() -> None:
    """No samples → items=[], total=0."""
    with TestClient(app) as c:
        dataset_id = _create_dataset(c, name="empty-ds")

        resp = c.get(f"/api/v1/datasets/{dataset_id}/samples-with-labels")
        assert resp.status_code == 200

        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0


# ---------------------------------------------------------------------------
# Test 5: Dataset not found → 404
# ---------------------------------------------------------------------------


def test_samples_with_labels_not_found() -> None:
    """GET with nonexistent dataset_id → 404."""
    with TestClient(app) as c:
        resp = c.get("/api/v1/datasets/nonexistent-dataset-id-xyz/samples-with-labels")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 6: Multiple annotations per sample — latest wins
# ---------------------------------------------------------------------------


def test_samples_with_labels_latest_annotation_wins() -> None:
    """Multiple annotations on same sample → latest by created_at is returned."""
    with TestClient(app) as c:
        dataset_id = _create_dataset(c, name="latest-ann-ds")
        s1 = _create_sample(c, dataset_id)

        # Create two annotations; second is newer
        _create_annotation(c, s1, "cat")
        _create_annotation(c, s1, "dog")  # this is newer

        resp = c.get(f"/api/v1/datasets/{dataset_id}/samples-with-labels")
        assert resp.status_code == 200
        body = resp.json()

        s1_item = next(item for item in body["items"] if item["id"] == s1)
        # Should return the latest annotation
        assert s1_item["latest_annotation"] is not None
        assert s1_item["latest_annotation"]["label"] == "dog"
