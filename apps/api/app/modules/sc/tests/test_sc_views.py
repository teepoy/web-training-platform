"""Integration tests for SC (semiconductor) view-type endpoints.

Covers the SC-specific view routers:
- GET /api/v1/datasets/{id}/views/patch_image_v1/samples
- GET /api/v1/datasets/{id}/views/review_image_v1/samples
- GET /api/v1/datasets/{id}/views/image_input_v1/samples  (generic datasets router)
- GET /api/v1/sc/images/{inspection_time}/{wafer_key}/{defect_id}/{image_type}
"""

from __future__ import annotations

import datetime
import unittest.mock as mock

from fastapi.testclient import TestClient

from app.main import app
from app.modules.auth.port.http.deps import get_current_org, get_current_user
from app.shared.api.schemas import Organization, User

_MOCK_USER = User(
    id="00000000-0000-0000-0000-000000000002",
    email="test@test.com",
    name="Test User",
    is_superadmin=True,
    is_active=True,
    created_at=datetime.datetime(2024, 1, 1),
)
_MOCK_ORG = Organization(
    id="00000000-0000-0000-0000-000000000001",
    name="Default",
    slug="default",
    created_at=datetime.datetime(2024, 1, 1),
)


def setup_function() -> None:
    app.dependency_overrides[get_current_user] = lambda: _MOCK_USER
    app.dependency_overrides[get_current_org] = lambda: _MOCK_ORG


def teardown_function() -> None:
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_org, None)

_SC_TASK_SPEC = {
    "task_type": "sc",
    "label_space": ["defect", "clean"],
}


def test_patch_image_v1_view_exists():
    """The SC-specific route returns 200 with correctly projected fields."""
    with TestClient(app) as client:
        # Create an image_sc dataset
        resp = client.post(
            "/api/v1/datasets",
            json={
                "name": "SC Test Patch View",
                "dataset_type": "image_sc",
                "task_spec": _SC_TASK_SPEC,
                "storage_mode": "db_full",
            },
        )
        assert resp.status_code == 200
        dataset_id = resp.json()["id"]

        # Add a sample with SC metadata
        resp2 = client.post(
            f"/api/v1/datasets/{dataset_id}/samples",
            json={
                "image_uris": ["http://example.com/img.png"],
                "metadata": {
                    "inspection_time": "2024-01-15T08:30:00",
                    "wafer_key": 1,
                    "defect_id": "D001",
                    "wafer_x": 23,
                    "wafer_y": 45,
                    "rough_bin": 1,
                },
            },
        )
        assert resp2.status_code == 200

        # Query the patch_image_v1 view on the SC-specific router
        resp3 = client.get(
            f"/api/v1/datasets/{dataset_id}/views/patch_image_v1/samples?limit=10"
        )
        assert resp3.status_code == 200
        data = resp3.json()
        assert "items" in data
        assert len(data["items"]) >= 1
        item = data["items"][0]
        assert "sample_id" in item
        assert item["inspection_time"] == "2024-01-15T08:30:00"
        assert item["wafer_key"] == 1
        assert item["defect_id"] == "D001"


def test_review_image_v1_projects_review_images():
    """review_image_v1 returns SC rows and preserves review_images when present."""
    with TestClient(app) as client:
        # Create dataset
        resp = client.post(
            "/api/v1/datasets",
            json={
                "name": "SC Test Review View",
                "dataset_type": "image_sc",
                "task_spec": _SC_TASK_SPEC,
                "storage_mode": "db_full",
            },
        )
        assert resp.status_code == 200
        dataset_id = resp.json()["id"]

        # Sample WITHOUT review_images (should still project with an empty list)
        sample_no_review = {
            "image_uris": ["http://example.com/img1.png"],
            "metadata": {
                "inspection_time": "2024-01-15T08:30:00",
                "wafer_key": 1,
                "defect_id": "D001",
            },
        }

        # Sample WITH review_images (should preserve review image metadata)
        sample_with_review = {
            "image_uris": ["http://example.com/img2.png"],
            "metadata": {
                "inspection_time": "2024-01-15T08:30:00",
                "wafer_key": 1,
                "defect_id": "D002",
                "review_images": [
                    {
                        "image_url": "http://ex.com/r1.png",
                        "image_name": "r1.png",
                        "image_id": 1,
                        "image_type": "review",
                    },
                ],
            },
        }

        # Create both samples via individual endpoints (no bulk endpoint)
        resp_a = client.post(
            f"/api/v1/datasets/{dataset_id}/samples",
            json=sample_no_review,
        )
        assert resp_a.status_code == 200

        resp_b = client.post(
            f"/api/v1/datasets/{dataset_id}/samples",
            json=sample_with_review,
        )
        assert resp_b.status_code == 200

        # Query review_image_v1
        resp3 = client.get(
            f"/api/v1/datasets/{dataset_id}/views/review_image_v1/samples?limit=10"
        )
        assert resp3.status_code == 200
        data = resp3.json()
        assert "items" in data
        assert len(data["items"]) == 2
        item = next(i for i in data["items"] if i["defect_id"] == "D002")
        assert "review_images" in item
        assert len(item["review_images"]) >= 1
        assert item["review_images"][0]["image_id"] == 1


def test_invalid_sc_view_returns_422():
    """A non-existent view type on the dataset view router returns 422."""
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/datasets",
            json={
                "name": "SC Test Invalid View",
                "dataset_type": "image_sc",
                "task_spec": _SC_TASK_SPEC,
                "storage_mode": "file_shard_sparse",
            },
        )
        assert resp.status_code == 200
        dataset_id = resp.json()["id"]

        # Access a view type that is not registered in the SC router
        resp2 = client.get(
            f"/api/v1/datasets/{dataset_id}/views/nonexistent_view_v1/samples"
        )
        assert resp2.status_code == 422
        detail = resp2.json()["detail"]
        assert "nonexistent_view_v1" in detail


def test_image_input_v1_not_supported_for_sc():
    """image_input_v1 view is not available for image_sc datasets."""
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/datasets",
            json={
                "name": "SC Image Input Not Supported",
                "dataset_type": "image_sc",
                "task_spec": _SC_TASK_SPEC,
                "storage_mode": "db_full",
            },
        )
        assert resp.status_code == 200
        dataset_id = resp.json()["id"]

        resp2 = client.post(
            f"/api/v1/datasets/{dataset_id}/samples",
            json={
                "image_uris": ["http://example.com/img.png"],
                "metadata": {},
            },
        )
        assert resp2.status_code == 200

        # image_input_v1 is not a valid view for image_sc datasets
        resp3 = client.get(
            f"/api/v1/datasets/{dataset_id}/views/image_input_v1/samples?limit=10"
        )
        assert resp3.status_code == 422


# ── Image serving endpoint tests ───────────────────────────────────────────────


def test_serve_patch_image_review_type_requires_review_image_id():
    """GET /api/v1/sc/images/.../review returns 400 when review_image_id is absent."""
    with TestClient(app) as client:
        resp = client.get(
            "/api/v1/sc/images/2024-01-01T00%3A00%3A00/1/DEF-001/review"
        )
        assert resp.status_code == 400
        assert "review_image_id" in resp.json()["detail"]


def test_serve_patch_image_review_type_with_review_image_id_fetches_review_bucket():
    """GET /api/v1/sc/images/.../review?review_image_id=5 uses the image fetcher."""
    fake_image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64  # minimal fake PNG

    with TestClient(app) as client:
        from app.modules.sc.port.http.deps import get_image_fetcher
        from app.modules.sc.adapter._wafer_mock.image_service import ScImageService

        mock_service = mock.AsyncMock(spec=ScImageService)
        mock_service.get_image_bytes = mock.AsyncMock(return_value=fake_image_bytes)

        app.dependency_overrides[get_image_fetcher] = lambda: mock_service
        try:
            resp = client.get(
                "/api/v1/sc/images/2024-01-01T00%3A00%3A00/1/DEF-001/review"
                "?review_image_id=5"
            )
            assert resp.status_code == 200
            assert resp.content == fake_image_bytes
            mock_service.get_image_bytes.assert_awaited_once_with(
                inspection_time="2024-01-01T00:00:00+00:00",
                wafer_key=1,
                defect_id="DEF-001",
                image_type="review",
                s3_path=None,
                review_image_id=5,
            )
        finally:
            app.dependency_overrides.pop(get_image_fetcher, None)


def test_serve_patch_image_invalid_image_type_returns_400():
    """GET /api/v1/sc/images/.../bad_type returns 400 for unknown image_type."""
    with TestClient(app) as client:
        resp = client.get(
            "/api/v1/sc/images/2024-01-01T00%3A00%3A00/1/DEF-001/bad_type"
        )
        assert resp.status_code == 400
        assert "image_type" in resp.json()["detail"]
