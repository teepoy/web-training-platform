"""Route-level tests for miscellaneous untested endpoints.

Covers:
- GET    /organizations
- DELETE /organizations/{org_id}/members/{user_id}
- POST   /task-tracker/tasks/{task_id}/cancel
- GET    /prediction-reviews/{action_id}/export
- POST   /prediction-reviews/{action_id}/export/persist
"""
from __future__ import annotations

import io
import json
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app, container
from tests.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID, PRESET_ID

_TASK_SPEC = {"task_type": "classification", "label_space": ["cat", "dog"]}


# ---------------------------------------------------------------------------
# Organizations
# ---------------------------------------------------------------------------

def test_list_organizations() -> None:
    """The mock user is superadmin, so list_all_organizations is called."""
    with TestClient(app) as c:
        resp = c.get("/api/v1/organizations")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


def test_remove_org_member_org_not_found() -> None:
    with TestClient(app) as c:
        resp = c.delete("/api/v1/organizations/nonexistent/members/some-user")
        assert resp.status_code == 404


def test_remove_org_member() -> None:
    """Create an org, register a real user, add them as member, then remove."""
    with TestClient(app) as c:
        # Register a real user in the DB
        reg = c.post("/api/v1/auth/register", json={
            "email": "member@test.com",
            "password": "pass1234",
            "name": "Member",
        })
        assert reg.status_code in (200, 201)
        member_user_id = reg.json()["id"]

        # Create org (mock user is superadmin)
        org_resp = c.post("/api/v1/organizations", json={"name": "test-org"})
        assert org_resp.status_code == 201
        org_id = org_resp.json()["id"]

        # Add the registered user as member
        add_resp = c.post(f"/api/v1/organizations/{org_id}/members", json={
            "user_id": member_user_id,
            "role": "member",
        })
        assert add_resp.status_code in (200, 201)

        # Remove member
        del_resp = c.delete(f"/api/v1/organizations/{org_id}/members/{member_user_id}")
        assert del_resp.status_code == 204


def test_remove_org_member_not_found() -> None:
    with TestClient(app) as c:
        org_resp = c.post("/api/v1/organizations", json={"name": "test-org-2"})
        assert org_resp.status_code == 201
        org_id = org_resp.json()["id"]

        resp = c.delete(f"/api/v1/organizations/{org_id}/members/nonexistent-user")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Task tracker cancel
# ---------------------------------------------------------------------------

def test_cancel_task_tracker_not_found() -> None:
    with TestClient(app) as c:
        resp = c.post("/api/v1/task-tracker/tasks/nonexistent/cancel")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Prediction review export
# ---------------------------------------------------------------------------

def _create_dataset(c: TestClient) -> str:
    resp = c.post("/api/v1/datasets", json={
        "name": "misc-ds",
        "dataset_type": "image_classification",
        "task_spec": _TASK_SPEC,
    })
    assert resp.status_code == 200
    return resp.json()["id"]


def _create_job(c: TestClient, dataset_id: str) -> str:
    resp = c.post("/api/v1/training-jobs", json={
        "dataset_id": dataset_id,
        "preset_id": PRESET_ID,
    })
    assert resp.status_code == 200
    return resp.json()["id"]


def _upload_model(c: TestClient, job_id: str) -> str:
    resp = c.post("/api/v1/models/upload", data={
        "metadata": json.dumps({
            "name": "test-model",
            "format": "pytorch",
            "job_id": job_id,
            "template_id": "image-classifier",
            "profile_id": "resnet50-cls-v1",
            "model_spec": {
                "framework": "pytorch",
                "architecture": "resnet50",
                "base_model": "torchvision/resnet50",
            },
            "compatibility": {
                "dataset_types": ["image_classification"],
                "task_types": ["classification"],
                "prediction_targets": ["image_classification"],
                "label_space": ["cat", "dog"],
            },
        }),
    }, files={"file": ("model.pt", io.BytesIO(b"fake-model"), "application/octet-stream")})
    assert resp.status_code == 200
    return resp.json()["id"]


def _create_sample(c: TestClient, dataset_id: str) -> str:
    resp = c.post(f"/api/v1/datasets/{dataset_id}/samples", json={
        "image_uris": [],
        "metadata": {},
    })
    assert resp.status_code == 200
    return resp.json()["id"]


def _setup_review(c: TestClient) -> tuple[str, str]:
    """Create dataset+model+review action+annotation versions. Returns (action_id, dataset_id)."""
    dataset_id = _create_dataset(c)
    job_id = _create_job(c, dataset_id)
    model_id = _upload_model(c, job_id)
    sample_id = _create_sample(c, dataset_id)

    # Create review action
    ra = c.post("/api/v1/prediction-reviews", json={
        "dataset_id": dataset_id,
        "model_id": model_id,
    })
    assert ra.status_code == 201
    action_id = ra.json()["id"]

    # Save annotations to create versions
    c.post(f"/api/v1/prediction-reviews/{action_id}/annotations", json={
        "items": [{
            "sample_id": sample_id,
            "predicted_label": "cat",
            "final_label": "dog",
            "confidence": 0.9,
        }],
    })

    return action_id, dataset_id


def test_export_review_version() -> None:
    with TestClient(app) as c:
        action_id, _ds = _setup_review(c)
        resp = c.get(f"/api/v1/prediction-reviews/{action_id}/export")
        assert resp.status_code == 200
        assert isinstance(resp.json(), dict)


def test_export_review_version_not_found() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/prediction-reviews/nonexistent/export")
        assert resp.status_code == 404


def test_export_review_version_bad_format() -> None:
    with TestClient(app) as c:
        action_id, _ds = _setup_review(c)
        resp = c.get(f"/api/v1/prediction-reviews/{action_id}/export", params={
            "format_id": "nonexistent-format",
        })
        assert resp.status_code == 400


def test_persist_review_export() -> None:
    with TestClient(app) as c:
        action_id, _ds = _setup_review(c)
        resp = c.post(f"/api/v1/prediction-reviews/{action_id}/export/persist", json={
            "format_id": "annotation-version-full-context-v1",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "uri" in body
        assert body["format_id"] == "annotation-version-full-context-v1"


def test_persist_review_export_not_found() -> None:
    with TestClient(app) as c:
        resp = c.post("/api/v1/prediction-reviews/nonexistent/export/persist", json={
            "format_id": "annotation-version-full-context-v1",
        })
        assert resp.status_code == 404


def test_persist_review_export_bad_format() -> None:
    with TestClient(app) as c:
        action_id, _ds = _setup_review(c)
        resp = c.post(f"/api/v1/prediction-reviews/{action_id}/export/persist", json={
            "format_id": "nonexistent-format",
        })
        assert resp.status_code == 400
