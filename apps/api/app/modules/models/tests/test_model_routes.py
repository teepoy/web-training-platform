"""Route-level tests for model endpoints.

Covers:
- GET    /models
- GET    /models/{model_id}
- DELETE /models/{model_id}
- GET    /models/{model_id}/download
"""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.auth.port.http.deps import get_current_user
from app.shared.api.schemas import User
from tests.conftest import TRAINER_ID, create_job, upload_model


def _setup(c: TestClient) -> tuple[str, str, str]:
    """Returns (dataset_id, job_id, model_id)."""
    resp = c.post(
        "/api/v1/datasets",
        json={
            "name": "test-sc-model-ds",
            "dataset_type": "image_sc",
            "task_spec": {"task_type": "sc", "label_space": ["defect", "clean"]},
        },
    )
    assert resp.status_code == 200, resp.text
    dataset_id = resp.json()["id"]
    for label in ("defect", "clean"):
        sample_resp = c.post(
            f"/api/v1/datasets/{dataset_id}/samples",
            json={"image_uris": []},
        )
        assert sample_resp.status_code == 200, sample_resp.text
        annotation_resp = c.post(
            "/api/v1/annotations",
            json={
                "dataset_id": dataset_id,
                "sample_id": sample_resp.json()["id"],
                "label": label,
                "created_by": "tester",
            },
        )
        assert annotation_resp.status_code == 200, annotation_resp.text
    job_id = create_job(c, dataset_id, trainer_id=TRAINER_ID)
    model_id = upload_model(c, job_id)
    return dataset_id, job_id, model_id


# ---------------------------------------------------------------------------
# List models
# ---------------------------------------------------------------------------

@pytest.mark.skip(reason="Pre-existing test isolation issue surfaced by module restructuring")
def test_list_models_empty() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/models")
        assert resp.status_code == 200
        assert resp.json() == {"items": [], "total": 0}


def test_get_model_not_found() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/models/nonexistent")
        assert resp.status_code == 404


def test_list_models_applies_search_and_creator_before_pagination() -> None:
    with TestClient(app) as c:
        _, _, model_id = _setup(c)

        searched = c.get("/api/v1/models?limit=1&q=test-model")
        missing_creator = c.get(
            "/api/v1/models?limit=1&creator_id=creator-who-does-not-exist"
        )
        creators = c.get("/api/v1/models/creators")

        assert searched.status_code == 200
        assert searched.json()["total"] == 1
        assert [item["id"] for item in searched.json()["items"]] == [model_id]
        assert missing_creator.status_code == 200
        assert missing_creator.json() == {"items": [], "total": 0}
        assert creators.status_code == 200
        assert any(
            creator["id"] == searched.json()["items"][0]["created_by"]
            for creator in creators.json()
        )


def test_download_model_not_found() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/models/nonexistent/download")
        assert resp.status_code == 404


def test_delete_model_not_found() -> None:
    with TestClient(app) as c:
        resp = c.delete("/api/v1/models/nonexistent")
        assert resp.status_code == 404


def _as_user(user_id: str) -> User:
    return User(
        id=user_id,
        email=f"{user_id}@example.com",
        name=user_id,
        is_superadmin=False,
        created_at=datetime(2024, 1, 1),
    )


def _with_current_user(user: User):
    original = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: user
    return original


def _restore_current_user(original) -> None:
    if original is None:
        app.dependency_overrides.pop(get_current_user, None)
    else:
        app.dependency_overrides[get_current_user] = original


def test_rename_model_requires_creator() -> None:
    with TestClient(app) as c:
        _, _, model_id = _setup(c)
        original = _with_current_user(_as_user("other-user"))
        try:
            resp = c.patch(
                f"/api/v1/models/{model_id}",
                json={"name": "should-not-rename"},
            )
        finally:
            _restore_current_user(original)

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Only the model creator can rename this model"


def test_delete_model_requires_creator() -> None:
    with TestClient(app) as c:
        _, _, model_id = _setup(c)
        original = _with_current_user(_as_user("other-user"))
        try:
            resp = c.delete(f"/api/v1/models/{model_id}")
        finally:
            _restore_current_user(original)

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Only the model creator can delete this model"
