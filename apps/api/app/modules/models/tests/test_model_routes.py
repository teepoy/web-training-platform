"""Route-level tests for model endpoints.

Covers:
- GET    /models
- GET    /models/{model_id}
- DELETE /models/{model_id}
- GET    /models/{model_id}/download
"""
from __future__ import annotations

import io
import json
from datetime import datetime

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.modules.auth.port.http.deps import get_current_user
from app.modules.models.app.services.model_service import ModelService
from app.shared.api.schemas import User
from tests.conftest import TRAINER_ID, create_job, model_artifact_bytes, upload_model


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


def test_model_artifact_upload_download_round_trip() -> None:
    with TestClient(app) as c:
        _, _, model_id = _setup(c)
        response = c.get(f"/api/v1/models/{model_id}/download")
        assert response.status_code == 200
        assert response.content == model_artifact_bytes()
        assert response.headers["content-length"] == str(len(model_artifact_bytes()))
        assert 'filename="test-model.pt"' in response.headers["content-disposition"]


def test_upload_model_accepts_minimal_runtime_owned_metadata() -> None:
    with TestClient(app) as c:
        dataset_id, _, _ = _setup(c)
        job_id = create_job(c, dataset_id, trainer_id=TRAINER_ID)
        response = c.post(
            "/api/v1/models/upload",
            data={
                "metadata": json.dumps(
                    {
                        "name": "minimal-model",
                        "format": "pytorch",
                        "job_id": job_id,
                    }
                )
            },
            files={
                "file": (
                    "minimal.pt",
                    io.BytesIO(model_artifact_bytes()),
                    "application/octet-stream",
                )
            },
        )

        assert response.status_code == 200, response.text
        assert response.json()["metadata"]["trainer_id"] == TRAINER_ID


def test_upload_model_rejects_invalid_trainer_artifact_without_publishing() -> None:
    with TestClient(app) as c:
        _, job_id, _ = _setup(c)
        before = c.get("/api/v1/models", params={"job_id": job_id}).json()["total"]
        response = c.post(
            "/api/v1/models/upload",
            data={
                "metadata": json.dumps(
                    {
                        "name": "invalid-model",
                        "format": "pytorch",
                        "job_id": job_id,
                    }
                )
            },
            files={
                "file": (
                    "invalid.pt",
                    io.BytesIO(b"not-a-checkpoint"),
                    "application/octet-stream",
                )
            },
        )
        after = c.get("/api/v1/models", params={"job_id": job_id}).json()["total"]

        assert response.status_code == 422, response.text
        assert "PyTorch ZIP checkpoint" in response.json()["detail"]
        assert after == before


def test_bounded_model_copy_rejects_payload_above_limit(tmp_path) -> None:
    with pytest.raises(HTTPException) as exc_info:
        ModelService._copy_bounded_upload(
            io.BytesIO(b"too-large"),
            tmp_path / "artifact",
            max_bytes=4,
        )

    assert exc_info.value.status_code == 413


def test_list_models_applies_search_and_creator_before_pagination() -> None:
    with TestClient(app) as c:
        _, _, model_id = _setup(c)

        searched = c.get("/api/v1/models?limit=1&q=test-model")
        missing_creator = c.get(
            "/api/v1/models?limit=1&creator_id=creator-who-does-not-exist"
        )
        collection_sources = c.get("/api/v1/models?source_type=collection")
        creators = c.get("/api/v1/models/creators")

        assert searched.status_code == 200
        assert searched.json()["total"] == 1
        assert [item["id"] for item in searched.json()["items"]] == [model_id]
        assert missing_creator.status_code == 200
        assert missing_creator.json() == {"items": [], "total": 0}
        assert collection_sources.status_code == 200
        assert collection_sources.json() == {"items": [], "total": 0}
        assert creators.status_code == 200
        assert any(
            creator["id"] == searched.json()["items"][0]["created_by"]
            for creator in creators.json()
        )


def test_list_models_sorts_before_pagination() -> None:
    with TestClient(app) as c:
        _, _, first_model_id = _setup(c)
        _, _, second_model_id = _setup(c)
        assert c.patch(
            f"/api/v1/models/{first_model_id}", json={"name": "Zulu model"}
        ).status_code == 200
        assert c.patch(
            f"/api/v1/models/{second_model_id}", json={"name": "Alpha model"}
        ).status_code == 200

        response = c.get(
            "/api/v1/models?sort_by=name&sort_order=asc&limit=1&offset=0"
        )

        assert response.status_code == 200
        assert response.json()["total"] == 2
        assert [item["name"] for item in response.json()["items"]] == ["Alpha model"]
        assert c.get("/api/v1/models?sort_order=sideways").status_code == 422


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


def test_uploaded_model_persists_runtime_contract() -> None:
    with TestClient(app) as c:
        _, _, model_id = _setup(c)

        resp = c.get(f"/api/v1/models/{model_id}")

        assert resp.status_code == 200, resp.text
        metadata = resp.json()["metadata"]
        assert metadata["model_contract"]
        assert metadata["model_schema_version"]
        assert metadata["trainer_id"]


def test_list_models_filters_by_registered_view_compatibility() -> None:
    with TestClient(app) as c:
        _, _, model_id = _setup(c)

        compatible = c.get(
            "/api/v1/models",
            params={"compatible_view_id": "patch_image_v1", "limit": 1},
        )
        incompatible = c.get(
            "/api/v1/models",
            params={"compatible_view_id": "image_input_v1", "limit": 1},
        )
        unknown = c.get(
            "/api/v1/models",
            params={"compatible_view_id": "not-a-registered-view"},
        )

        assert compatible.status_code == 200, compatible.text
        assert compatible.json()["total"] == 1
        assert [item["id"] for item in compatible.json()["items"]] == [model_id]
        assert incompatible.status_code == 200, incompatible.text
        assert incompatible.json() == {"items": [], "total": 0}
        assert unknown.status_code == 422, unknown.text
        assert unknown.json()["detail"] == (
            "Unknown compatible view: not-a-registered-view"
        )


def test_delete_model_preserves_other_artifacts_from_same_training_job() -> None:
    with TestClient(app) as c:
        _, job_id, first_model_id = _setup(c)
        second_model_id = upload_model(c, job_id)

        deleted = c.delete(f"/api/v1/models/{first_model_id}")
        remaining = c.get(f"/api/v1/models/{second_model_id}")
        remaining_download = c.get(f"/api/v1/models/{second_model_id}/download")

        assert deleted.status_code == 204, deleted.text
        assert remaining.status_code == 200, remaining.text
        assert remaining_download.status_code == 200, remaining_download.text


def test_upload_model_requires_training_job_creator() -> None:
    with TestClient(app) as c:
        _, job_id, _ = _setup(c)
        metadata = json.dumps(
            {
                "name": "unauthorized-model",
                "format": "pytorch",
                "job_id": job_id,
                "template_id": "image-classifier",
                "profile_id": "custom",
                "model_spec": {},
                "compatibility": {
                    "dataset_types": ["image_classification"],
                    "task_types": ["classification"],
                    "prediction_targets": ["image_classification"],
                    "label_space": ["defect", "clean"],
                },
            }
        )
        original = _with_current_user(_as_user("other-user"))
        try:
            resp = c.post(
                "/api/v1/models/upload",
                data={"metadata": metadata},
                files={
                    "file": (
                        "model.pt",
                        io.BytesIO(b"not-authorized"),
                        "application/octet-stream",
                    )
                },
            )
        finally:
            _restore_current_user(original)

        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == (
            "Only the training job creator can upload its model artifacts"
        )
