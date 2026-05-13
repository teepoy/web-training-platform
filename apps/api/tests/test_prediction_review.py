from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import create_dataset, create_sample, create_job, upload_model

def _setup_dataset_with_model(c: TestClient) -> tuple[str, str, str]:
    """Create dataset + job + model, return (dataset_id, model_id, job_id)."""
    dataset_id = create_dataset(c)
    job_id = create_job(c, dataset_id)
    model_id = upload_model(c, job_id)
    return dataset_id, model_id, job_id


# ---------------------------------------------------------------------------
# Test: Create review action
# ---------------------------------------------------------------------------


def test_create_review_action() -> None:
    with TestClient(app) as c:
        dataset_id, model_id, _ = _setup_dataset_with_model(c)

        resp = c.post(
            "/api/v1/prediction-reviews",
            json={"dataset_id": dataset_id, "model_id": model_id},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["dataset_id"] == dataset_id
        assert body["model_id"] == model_id
        assert body["model_version"] is None
        assert "id" in body
        assert "created_at" in body


# ---------------------------------------------------------------------------
# Test: Create review action with model_version
# ---------------------------------------------------------------------------


def test_create_review_action_with_version() -> None:
    with TestClient(app) as c:
        dataset_id, model_id, _ = _setup_dataset_with_model(c)

        resp = c.post(
            "/api/v1/prediction-reviews",
            json={
                "dataset_id": dataset_id,
                "model_id": model_id,
                "model_version": "v2.1",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["model_version"] == "v2.1"


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
# Test: List review actions
# ---------------------------------------------------------------------------


def test_list_review_actions() -> None:
    with TestClient(app) as c:
        dataset_id, model_id, _ = _setup_dataset_with_model(c)

        # Create two review actions
        c.post("/api/v1/prediction-reviews", json={"dataset_id": dataset_id, "model_id": model_id})
        c.post("/api/v1/prediction-reviews", json={"dataset_id": dataset_id, "model_id": model_id})

        resp = c.get(f"/api/v1/prediction-reviews?dataset_id={dataset_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert all(a["dataset_id"] == dataset_id for a in body)


# ---------------------------------------------------------------------------
# Test: List review actions requires dataset_id query param
# ---------------------------------------------------------------------------


def test_list_review_actions_requires_dataset_id() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/prediction-reviews")
        assert resp.status_code == 422  # validation error


# ---------------------------------------------------------------------------
# Test: Get single review action
# ---------------------------------------------------------------------------


def test_get_review_action() -> None:
    with TestClient(app) as c:
        dataset_id, model_id, _ = _setup_dataset_with_model(c)

        create_resp = c.post(
            "/api/v1/prediction-reviews",
            json={"dataset_id": dataset_id, "model_id": model_id},
        )
        action_id = create_resp.json()["id"]

        resp = c.get(f"/api/v1/prediction-reviews/{action_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == action_id


# ---------------------------------------------------------------------------
# Test: Get non-existent review action → 404
# ---------------------------------------------------------------------------


def test_get_review_action_not_found() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/prediction-reviews/nonexistent-id")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: Delete review action
# ---------------------------------------------------------------------------


def test_delete_review_action() -> None:
    with TestClient(app) as c:
        dataset_id, model_id, _ = _setup_dataset_with_model(c)

        create_resp = c.post(
            "/api/v1/prediction-reviews",
            json={"dataset_id": dataset_id, "model_id": model_id},
        )
        action_id = create_resp.json()["id"]

        resp = c.delete(f"/api/v1/prediction-reviews/{action_id}")
        assert resp.status_code == 204

        # Verify it's gone
        resp = c.get(f"/api/v1/prediction-reviews/{action_id}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: Delete non-existent review action → 404
# ---------------------------------------------------------------------------


def test_delete_review_action_not_found() -> None:
    with TestClient(app) as c:
        resp = c.delete("/api/v1/prediction-reviews/nonexistent-id")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: Save review annotations
# ---------------------------------------------------------------------------


def test_save_review_annotations() -> None:
    with TestClient(app) as c:
        dataset_id, model_id, _ = _setup_dataset_with_model(c)
        sample_id = create_sample(c, dataset_id)

        # Create review action
        create_resp = c.post(
            "/api/v1/prediction-reviews",
            json={"dataset_id": dataset_id, "model_id": model_id},
        )
        assert create_resp.status_code == 201
        action_id = create_resp.json()["id"]

        # Save reviewed annotations
        resp = c.post(
            f"/api/v1/prediction-reviews/{action_id}/annotations",
            json={
                "items": [
                    {
                        "sample_id": sample_id,
                        "predicted_label": "cat",
                        "final_label": "dog",
                        "confidence": 0.85,
                        "prediction_id": None,
                    },
                ],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["review_action_id"] == action_id
        assert body["created_count"] == 1
        assert len(body["annotation_versions"]) == 1

        version = body["annotation_versions"][0]
        assert version["predicted_label"] == "cat"
        assert version["final_label"] == "dog"
        assert version["confidence"] == 0.85
        assert version["review_action_id"] == action_id


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
# Test: List annotation versions
# ---------------------------------------------------------------------------


def test_list_annotation_versions() -> None:
    with TestClient(app) as c:
        dataset_id, model_id, _ = _setup_dataset_with_model(c)
        sample_id_1 = create_sample(c, dataset_id)
        sample_id_2 = create_sample(c, dataset_id)

        # Create action and save annotations
        create_resp = c.post(
            "/api/v1/prediction-reviews",
            json={"dataset_id": dataset_id, "model_id": model_id},
        )
        action_id = create_resp.json()["id"]

        c.post(
            f"/api/v1/prediction-reviews/{action_id}/annotations",
            json={
                "items": [
                    {
                        "sample_id": sample_id_1,
                        "predicted_label": "cat",
                        "final_label": "cat",
                        "confidence": 0.9,
                        "prediction_id": None,
                    },
                    {
                        "sample_id": sample_id_2,
                        "predicted_label": "dog",
                        "final_label": "bird",
                        "confidence": 0.6,
                        "prediction_id": None,
                    },
                ],
            },
        )

        # List versions
        resp = c.get(f"/api/v1/prediction-reviews/{action_id}/annotation-versions")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2

        labels = {v["final_label"] for v in body}
        assert labels == {"cat", "bird"}


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
# Test: Preview export
# ---------------------------------------------------------------------------


def test_preview_export() -> None:
    with TestClient(app) as c:
        dataset_id, model_id, _ = _setup_dataset_with_model(c)
        sample_id = create_sample(c, dataset_id)

        # Create action + save annotations
        create_resp = c.post(
            "/api/v1/prediction-reviews",
            json={"dataset_id": dataset_id, "model_id": model_id},
        )
        action_id = create_resp.json()["id"]

        c.post(
            f"/api/v1/prediction-reviews/{action_id}/annotations",
            json={
                "items": [
                    {
                        "sample_id": sample_id,
                        "predicted_label": "cat",
                        "final_label": "dog",
                        "confidence": 0.7,
                        "prediction_id": None,
                    },
                ],
            },
        )

        # Preview with full-context format
        resp = c.get(
            f"/api/v1/prediction-reviews/{action_id}/export",
            params={"format_id": "annotation-version-full-context-v1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["format"] == "annotation-version-full-context-v1"
        assert "review_action" in body
        assert "dataset" in body
        assert "samples" in body
        assert "annotations" in body
        assert len(body["samples"]) == 1
        assert len(body["annotations"]) == 1


# ---------------------------------------------------------------------------
# Test: Preview export with compact format
# ---------------------------------------------------------------------------


def test_preview_export_compact() -> None:
    with TestClient(app) as c:
        dataset_id, model_id, _ = _setup_dataset_with_model(c)
        sample_id = create_sample(c, dataset_id)

        create_resp = c.post(
            "/api/v1/prediction-reviews",
            json={"dataset_id": dataset_id, "model_id": model_id},
        )
        action_id = create_resp.json()["id"]

        c.post(
            f"/api/v1/prediction-reviews/{action_id}/annotations",
            json={
                "items": [
                    {
                        "sample_id": sample_id,
                        "predicted_label": "cat",
                        "final_label": "cat",
                        "confidence": 0.95,
                        "prediction_id": None,
                    },
                ],
            },
        )

        resp = c.get(
            f"/api/v1/prediction-reviews/{action_id}/export",
            params={"format_id": "annotation-version-compact-v1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["format"] == "annotation-version-compact-v1"
        assert "rows" in body


# ---------------------------------------------------------------------------
# Test: Preview export unknown format → 400
# ---------------------------------------------------------------------------


def test_preview_export_unknown_format() -> None:
    with TestClient(app) as c:
        dataset_id, model_id, _ = _setup_dataset_with_model(c)

        create_resp = c.post(
            "/api/v1/prediction-reviews",
            json={"dataset_id": dataset_id, "model_id": model_id},
        )
        action_id = create_resp.json()["id"]

        resp = c.get(
            f"/api/v1/prediction-reviews/{action_id}/export",
            params={"format_id": "nonexistent-format"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Test: Preview export non-existent action → 404
# ---------------------------------------------------------------------------


def test_preview_export_not_found() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/prediction-reviews/nonexistent/export")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: Persist export
# ---------------------------------------------------------------------------


def test_persist_export() -> None:
    with TestClient(app) as c:
        dataset_id, model_id, _ = _setup_dataset_with_model(c)
        sample_id = create_sample(c, dataset_id)

        create_resp = c.post(
            "/api/v1/prediction-reviews",
            json={"dataset_id": dataset_id, "model_id": model_id},
        )
        action_id = create_resp.json()["id"]

        c.post(
            f"/api/v1/prediction-reviews/{action_id}/annotations",
            json={
                "items": [
                    {
                        "sample_id": sample_id,
                        "predicted_label": "cat",
                        "final_label": "dog",
                        "confidence": 0.8,
                        "prediction_id": None,
                    },
                ],
            },
        )

        resp = c.post(
            f"/api/v1/prediction-reviews/{action_id}/export/persist",
            json={"format_id": "annotation-version-full-context-v1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "uri" in body
        assert body["format_id"] == "annotation-version-full-context-v1"
