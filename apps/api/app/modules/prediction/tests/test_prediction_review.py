from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.shared.api.schemas import PredictionReviewAction
from app.shared.db.models.auth import OrganizationORM
from app.shared.db.models.datasets import DatasetORM
from tests.conftest import (
    DEFAULT_ORG_ID,
    create_dataset,
    create_job,
    upload_model,
)

def _setup_dataset_with_model(c: TestClient) -> tuple[str, str, str]:
    """Create dataset + job + model, return (dataset_id, model_id, job_id)."""
    dataset_id = create_dataset(c)
    job_id = create_job(c, dataset_id)
    model_id = upload_model(c, job_id)
    return dataset_id, model_id, job_id


# ---------------------------------------------------------------------------
# Test: Create review action with bad dataset → 400
# ---------------------------------------------------------------------------


def test_create_review_action_bad_dataset() -> None:
    with TestClient(app) as c:
        resp = c.post(
            "/api/v1/prediction-reviews",
            json={"dataset_id": "nonexistent", "model_id": "nonexistent"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Test: List review actions requires dataset_id query param
# ---------------------------------------------------------------------------


def test_list_review_actions_requires_dataset_id() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/prediction-reviews")
        assert resp.status_code == 422  # validation error


# ---------------------------------------------------------------------------
# Test: Get non-existent review action → 404
# ---------------------------------------------------------------------------


def test_get_review_action_not_found() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/prediction-reviews/nonexistent-id")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: Delete non-existent review action → 404
# ---------------------------------------------------------------------------


def test_delete_review_action_not_found() -> None:
    with TestClient(app) as c:
        resp = c.delete("/api/v1/prediction-reviews/nonexistent-id")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: Save review annotations for non-existent action → 400
# ---------------------------------------------------------------------------


def test_save_review_annotations_bad_action() -> None:
    with TestClient(app) as c:
        resp = c.post(
            "/api/v1/prediction-reviews/nonexistent-id/annotations",
            json={
                "items": [
                    {
                        "sample_id": "some-sample",
                        "predicted_label": "cat",
                        "final_label": "dog",
                        "confidence": None,
                        "prediction_id": None,
                    },
                ],
            },
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: List annotation versions for non-existent action → 404
# ---------------------------------------------------------------------------


def test_list_annotation_versions_not_found() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/prediction-reviews/nonexistent/annotation-versions")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: List export formats
# ---------------------------------------------------------------------------


def test_list_export_formats() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/export-formats")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        format_ids = {f["format_id"] for f in body}
        assert "annotation-version-full-context-v1" in format_ids
        assert "annotation-version-compact-v1" in format_ids


# ---------------------------------------------------------------------------
# Test: Preview export non-existent action → 404
# ---------------------------------------------------------------------------


def test_preview_export_not_found() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/prediction-reviews/nonexistent/export")
        assert resp.status_code == 404


def test_review_actions_are_scoped_to_dataset_organization() -> None:
    other_org_id = "00000000-0000-0000-0000-000000000099"
    dataset_id = f"other-org-dataset-{uuid4()}"
    action = PredictionReviewAction(
        dataset_id=dataset_id,
        model_id="model-other-org",
        created_by="user-other-org",
    )

    with TestClient(app):
        context = app.state.app_context
        repository = context.prediction.prediction_repository

        async def verify_scope() -> None:
            async with context.shared.session_factory.sessionmaker() as session:
                session.add(
                    OrganizationORM(
                        id=other_org_id,
                        name="Other Org",
                        slug=f"other-org-{uuid4()}",
                    )
                )
                session.add(
                    DatasetORM(
                        id=dataset_id,
                        org_id=other_org_id,
                        name="Other Org Dataset",
                        dataset_type="image_classification",
                        view_types=[],
                        dataset_meta={
                            "task_type": "classification",
                            "label_space": ["cat", "dog"],
                        },
                        created_by="user-other-org",
                        ls_project_id="1",
                        storage_mode="db_full",
                    )
                )
                await session.commit()

            await repository.create_review_action(action)

            assert await repository.get_review_action(action.id, DEFAULT_ORG_ID) is None
            assert (
                await repository.list_review_actions(dataset_id, DEFAULT_ORG_ID) == []
            )
            assert (
                await repository.delete_review_action(action.id, DEFAULT_ORG_ID)
                is False
            )

            assert (
                await repository.get_review_action(action.id, other_org_id) is not None
            )
            assert await repository.delete_review_action(action.id, other_org_id) is True

        asyncio.run(verify_scope())
