from __future__ import annotations

"""RED tests for per-view dataset sample endpoint.

Endpoint: GET /api/v1/datasets/{dataset_id}/views/{view_type}/samples

These tests define the expected contract before the route is implemented.
They will FAIL (RED) until Task 12 implements the handler.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.skip(
    reason="DatasetSessionFactory requires storage-agg migration — session/view layer deferred"
)


# ---------------------------------------------------------------------------
# 1. 404 — nonexistent dataset
# ---------------------------------------------------------------------------


def test_per_view_endpoint_returns_404_for_nonexistent_dataset() -> None:
    """Endpoint returns 404 when dataset_id does not exist."""
    with TestClient(app) as client:
        resp = client.get(
            "/api/v1/datasets/nonexistent-dataset-id-99999/views/labeled_image_v1/samples"
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 2. 422 — invalid / unsupported view type
# ---------------------------------------------------------------------------


def test_per_view_endpoint_returns_422_for_invalid_view_type() -> None:
    """Endpoint returns 422 when view_type is not in the registry."""
    with TestClient(app) as client:
        # Create a real dataset so the dataset lookup succeeds
        ds = client.post(
            "/api/v1/datasets",
            json={
                "name": "ds-422-view",
                "dataset_type": "image_classification",
                "task_spec": {
                    "task_type": "classification",
                    "label_space": ["cat", "dog"],
                },
            },
        )
        assert ds.status_code == 200
        dataset_id = ds.json()["id"]

        # Request a view type that does NOT exist in the registry
        resp = client.get(
            f"/api/v1/datasets/{dataset_id}/views/nonexistent_view_type_v999/samples"
        )
        assert resp.status_code == 422
        detail = resp.json().get("detail", "")
        assert "view" in detail.lower()


def test_per_view_endpoint_returns_422_for_disabled_view_type() -> None:
    """Endpoint returns 422 when view_type exists but is not enabled for this dataset."""
    with TestClient(app) as client:
        # Create classification dataset — will NOT have box_detection_v1 in view_types
        ds = client.post(
            "/api/v1/datasets",
            json={
                "name": "ds-disabled-view",
                "dataset_type": "image_classification",
                "task_spec": {
                    "task_type": "classification",
                    "label_space": ["cat", "dog"],
                },
            },
        )
        assert ds.status_code == 200
        dataset_id = ds.json()["id"]

        # box_detection_v1 is registered but this dataset is classification —
        # it should NOT be enabled
        resp = client.get(
            f"/api/v1/datasets/{dataset_id}/views/box_detection_v1/samples"
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 3. Empty dataset — valid pagination metadata with empty items
# ---------------------------------------------------------------------------


def test_per_view_endpoint_handles_empty_dataset() -> None:
    """Empty dataset returns items=[], total=0 with valid pagination metadata."""
    with TestClient(app) as client:
        ds = client.post(
            "/api/v1/datasets",
            json={
                "name": "ds-empty",
                "dataset_type": "image_classification",
                "task_spec": {
                    "task_type": "classification",
                    "label_space": ["cat", "dog"],
                },
            },
        )
        assert ds.status_code == 200
        dataset_id = ds.json()["id"]

        resp = client.get(
            f"/api/v1/datasets/{dataset_id}/views/labeled_image_v1/samples"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert body["view_type"] == "labeled_image_v1"
        assert body["dataset_id"] == dataset_id
        assert body["limit"] > 0
        assert body["offset"] == 0


# ---------------------------------------------------------------------------
# 4. Classification view (labeled_image_v1) — typed rows
# ---------------------------------------------------------------------------


def test_per_view_endpoint_returns_rows_for_labeled_image_v1() -> None:
    """Classification dataset returns {sample_id, image_uris, label} items."""
    with TestClient(app) as client:
        # Create classification dataset
        ds = client.post(
            "/api/v1/datasets",
            json={
                "name": "ds-classify",
                "dataset_type": "image_classification",
                "task_spec": {
                    "task_type": "classification",
                    "label_space": ["cat", "dog", "bird"],
                },
            },
        )
        assert ds.status_code == 200
        dataset_id = ds.json()["id"]

        # Create samples with labels via bulk import
        import_resp = client.post(
            f"/api/v1/datasets/{dataset_id}/samples/import",
            json={
                "items": [
                    {
                        "image_uris": ["memory://ds-classify/img-1.png"],
                        "metadata": {},
                        "label": "cat",
                    },
                    {
                        "image_uris": ["memory://ds-classify/img-2.png"],
                        "metadata": {},
                        "label": "dog",
                    },
                    {
                        "image_uris": ["memory://ds-classify/img-3.png"],
                        "metadata": {},
                        "label": "cat",
                    },
                ]
            },
        )
        assert import_resp.status_code == 200
        assert import_resp.json()["imported"] == 3

        # Hit the per-view endpoint
        resp = client.get(
            f"/api/v1/datasets/{dataset_id}/views/labeled_image_v1/samples"
        )
        assert resp.status_code == 200
        body = resp.json()

        # Pagination envelope
        assert body["view_type"] == "labeled_image_v1"
        assert body["dataset_id"] == dataset_id
        assert body["total"] == 3
        assert body["limit"] > 0
        assert body["offset"] == 0

        # Typed row fields
        items = body["items"]
        assert len(items) == 3
        for item in items:
            assert "sample_id" in item
            assert isinstance(item["image_uris"], list)
            assert "label" in item
            # label should be one of the label_space values
            assert item["label"] in ("cat", "dog", "bird")


# ---------------------------------------------------------------------------
# 5. VQA view (qa_input_v1) — typed rows
# ---------------------------------------------------------------------------


def test_per_view_endpoint_returns_rows_for_qa_input_v1() -> None:
    """VQA dataset returns {sample_id, image_uris, question} items."""
    with TestClient(app) as client:
        # Create VQA dataset
        ds = client.post(
            "/api/v1/datasets",
            json={
                "name": "ds-vqa",
                "dataset_type": "image_vqa",
                "task_spec": {
                    "task_type": "vqa",
                    "label_space": [],
                },
            },
        )
        assert ds.status_code == 200
        dataset_id = ds.json()["id"]

        # Create VQA samples
        for i, q in enumerate(["What color?", "How many?", "Where?"], start=100):
            s = client.post(
                f"/api/v1/datasets/{dataset_id}/samples",
                json={
                    "image_uris": [f"memory://ds-vqa/img-{i}.png"],
                    "metadata": {"question": q},
                },
            )
            assert s.status_code == 200

        resp = client.get(
            f"/api/v1/datasets/{dataset_id}/views/qa_input_v1/samples"
        )
        assert resp.status_code == 200
        body = resp.json()

        assert body["view_type"] == "qa_input_v1"
        assert body["dataset_id"] == dataset_id
        assert body["total"] == 3

        items = body["items"]
        assert len(items) == 3
        for item in items:
            assert "sample_id" in item
            assert isinstance(item["image_uris"], list)
            assert "question" in item
            assert isinstance(item["question"], str)


# ---------------------------------------------------------------------------
# 6. Detection view (box_detection_v1) — typed rows
# ---------------------------------------------------------------------------


def test_per_view_endpoint_returns_rows_for_box_detection_v1() -> None:
    """Detection dataset returns {sample_id, image_uris, boxes, width?, height?} items."""
    with TestClient(app) as client:
        ds = client.post(
            "/api/v1/datasets",
            json={
                "name": "ds-detection",
                "dataset_type": "image_detection",
                "task_spec": {
                    "task_type": "detection",
                    "label_space": ["person", "car"],
                },
            },
        )
        assert ds.status_code == 200
        dataset_id = ds.json()["id"]

        # Create detection samples via import
        import_resp = client.post(
            f"/api/v1/datasets/{dataset_id}/samples/import",
            json={
                "items": [
                    {
                        "image_uris": ["memory://ds-detection/img-1.png"],
                        "metadata": {},
                        "label": "person",
                    },
                    {
                        "image_uris": ["memory://ds-detection/img-2.png"],
                        "metadata": {},
                        "label": "car",
                    },
                ]
            },
        )
        assert import_resp.status_code == 200
        assert import_resp.json()["imported"] == 2

        resp = client.get(
            f"/api/v1/datasets/{dataset_id}/views/box_detection_v1/samples"
        )
        assert resp.status_code == 200
        body = resp.json()

        assert body["view_type"] == "box_detection_v1"
        assert body["dataset_id"] == dataset_id
        assert body["total"] == 2

        items = body["items"]
        assert len(items) == 2
        for item in items:
            assert "sample_id" in item
            assert isinstance(item["image_uris"], list)
            assert "boxes" in item
            assert isinstance(item["boxes"], list)
            # width and height are optional per BoxDetectionV1 schema
            # they may or may not be present


# ---------------------------------------------------------------------------
# 7. Pagination — limit/offset produce correct partial results
# ---------------------------------------------------------------------------


def test_per_view_pagination_works() -> None:
    """limit/offset produce correct partial results and reflect in response metadata."""
    with TestClient(app) as client:
        ds = client.post(
            "/api/v1/datasets",
            json={
                "name": "ds-paginated",
                "dataset_type": "image_classification",
                "task_spec": {
                    "task_type": "classification",
                    "label_space": ["cat", "dog"],
                },
            },
        )
        assert ds.status_code == 200
        dataset_id = ds.json()["id"]

        # Create 10 samples via bulk import
        items = [
            {
                "image_uris": [f"memory://ds-paginated/img-{i}.png"],
                "metadata": {},
                "label": "cat" if i % 2 == 0 else "dog",
            }
            for i in range(10)
        ]
        import_resp = client.post(
            f"/api/v1/datasets/{dataset_id}/samples/import",
            json={"items": items},
        )
        assert import_resp.status_code == 200
        assert import_resp.json()["imported"] == 10

        # Page 1: limit=4 offset=0
        page1 = client.get(
            f"/api/v1/datasets/{dataset_id}/views/labeled_image_v1/samples"
            "?limit=4&offset=0"
        )
        assert page1.status_code == 200
        p1 = page1.json()
        assert len(p1["items"]) == 4
        assert p1["total"] == 10
        assert p1["limit"] == 4
        assert p1["offset"] == 0

        # Page 2: limit=4 offset=4
        page2 = client.get(
            f"/api/v1/datasets/{dataset_id}/views/labeled_image_v1/samples"
            "?limit=4&offset=4"
        )
        assert page2.status_code == 200
        p2 = page2.json()
        assert len(p2["items"]) == 4
        assert p2["total"] == 10
        assert p2["limit"] == 4
        assert p2["offset"] == 4

        # Page 3 (partial): limit=4 offset=8
        page3 = client.get(
            f"/api/v1/datasets/{dataset_id}/views/labeled_image_v1/samples"
            "?limit=4&offset=8"
        )
        assert page3.status_code == 200
        p3 = page3.json()
        assert len(p3["items"]) == 2  # only 2 remaining
        assert p3["total"] == 10
        assert p3["limit"] == 4
        assert p3["offset"] == 8

        # Verify items are distinct across pages (no overlap)
        ids_page1 = {item["sample_id"] for item in p1["items"]}
        ids_page2 = {item["sample_id"] for item in p2["items"]}
        ids_page3 = {item["sample_id"] for item in p3["items"]}
        assert ids_page1.isdisjoint(ids_page2)
        assert ids_page1.isdisjoint(ids_page3)
        assert ids_page2.isdisjoint(ids_page3)
        all_ids = ids_page1 | ids_page2 | ids_page3
        assert len(all_ids) == 10


# ---------------------------------------------------------------------------
# 8. Default pagination — no query params uses sensible defaults
# ---------------------------------------------------------------------------


def test_per_view_endpoint_default_pagination() -> None:
    """When no limit/offset provided, defaults produce a valid first page."""
    with TestClient(app) as client:
        ds = client.post(
            "/api/v1/datasets",
            json={
                "name": "ds-default-page",
                "dataset_type": "image_classification",
                "task_spec": {
                    "task_type": "classification",
                    "label_space": ["cat", "dog"],
                },
            },
        )
        assert ds.status_code == 200
        dataset_id = ds.json()["id"]

        # Create 5 samples
        items = [
            {
                "image_uris": [f"memory://ds-default-page/img-{i}.png"],
                "metadata": {},
                "label": "cat",
            }
            for i in range(5)
        ]
        import_resp = client.post(
            f"/api/v1/datasets/{dataset_id}/samples/import",
            json={"items": items},
        )
        assert import_resp.status_code == 200

        resp = client.get(
            f"/api/v1/datasets/{dataset_id}/views/labeled_image_v1/samples"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 5
        assert body["offset"] == 0
        assert body["limit"] > 0
        assert len(body["items"]) == min(5, body["limit"])
