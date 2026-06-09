from __future__ import annotations

import datetime

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

"""Tests for GET /api/v1/datasets/{dataset_id} — dataset detail.

Verifies that the handler returns a typed Dataset response
with all expected keys and correct types, and that missing datasets
return a documented 404 error.
"""


def test_sc_dataset_detail_returns_all_expected_keys() -> None:
    """Normal dataset detail returns all Dataset fields."""
    with TestClient(app) as client:
        # Create an image_sc dataset
        resp = client.post(
            "/api/v1/datasets",
            json={
                "name": "SC Detail Test",
                "dataset_type": "image_sc",
                "task_spec": {
                    "task_type": "sc",
                    "label_space": ["defect", "clean"],
                },
                "view_types": ["patch_image_v1", "review_image_v1"],
            },
        )
        assert resp.status_code == 200
        dataset_id = resp.json()["id"]

        # Fetch dataset detail
        resp2 = client.get(f"/api/v1/datasets/{dataset_id}")
        assert resp2.status_code == 200
        body = resp2.json()

        # All expected keys are present
        assert "id" in body
        assert "name" in body
        assert "dataset_type" in body
        assert "task_spec" in body
        assert "view_types" in body
        assert "org_id" in body
        assert "created_at" in body
        assert "storage_mode" in body
        assert "ls_project_id" in body

        # Value checks
        assert body["id"] == dataset_id
        assert body["name"] == "SC Detail Test"
        assert body["dataset_type"] == "image_sc"
        assert body["task_spec"]["task_type"] == "sc"
        assert body["task_spec"]["label_space"] == ["defect", "clean"]
        assert isinstance(body["task_spec"], dict)
        assert isinstance(body["view_types"], list)
        assert isinstance(body["created_at"], str)
        assert isinstance(body["storage_mode"], str)


def test_sc_dataset_detail_fields_have_correct_types() -> None:
    """All response fields have the expected Python/JSON types."""
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/datasets",
            json={
                "name": "SC Type Check",
                "dataset_type": "image_sc",
                "task_spec": {
                    "task_type": "sc",
                    "label_space": [],
                },
            },
        )
        assert resp.status_code == 200
        dataset_id = resp.json()["id"]

        resp2 = client.get(f"/api/v1/datasets/{dataset_id}")
        assert resp2.status_code == 200
        body = resp2.json()

        # String fields
        assert isinstance(body["id"], str)
        assert isinstance(body["name"], str)
        assert isinstance(body["dataset_type"], str)
        assert isinstance(body["org_id"], str)
        assert isinstance(body["created_at"], str)
        assert isinstance(body["storage_mode"], str)

        # Container fields
        assert isinstance(body["task_spec"], dict)
        assert isinstance(body["view_types"], list)

        # Nullable string field
        assert isinstance(body["ls_project_id"], (str, type(None)))


def test_sc_dataset_detail_missing_returns_404() -> None:
    """Non-existent dataset returns 404 with documented error message."""
    with TestClient(app) as client:
        resp = client.get("/api/v1/datasets/nonexistent-dataset-12345")
        assert resp.status_code == 404
        assert "detail" in resp.json()


def test_sc_dataset_detail_with_sparse_storage_mode() -> None:
    """Storage mode is serialized as a string, not an enum value."""
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/datasets",
            json={
                "name": "SC Sparse Storage",
                "dataset_type": "image_sc",
                "storage_mode": "file_shard_sparse",
                "task_spec": {
                    "task_type": "sc",
                    "label_space": ["defect"],
                },
            },
        )
        assert resp.status_code == 200
        dataset_id = resp.json()["id"]

        resp2 = client.get(f"/api/v1/datasets/{dataset_id}")
        assert resp2.status_code == 200
        body = resp2.json()

        assert isinstance(body["storage_mode"], str)
        assert body["storage_mode"] != ""
