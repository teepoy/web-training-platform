from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.registry import list_predictors
from app.main import app


def test_trainer_catalog_endpoint_preserves_baseline_shape() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/trainers")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert body, "trainer catalog should not be empty"

    for row in body:
        assert set(row) >= {"id", "name", "view_type", "trainable"}
        assert isinstance(row["id"], str)
        assert isinstance(row["name"], str)
        assert isinstance(row["view_type"], str)
        assert row["trainable"] is True

    trainer_ids = {row["id"] for row in body}
    assert {"resnet50-sc-v1", "resnet50-sc-v1", "resnet50-sc-v1", "resnet50-sc-v1", "yolo-sc-v1"} <= trainer_ids


def test_predictor_catalog_listing_preserves_baseline_shape() -> None:
    body = list_predictors()

    assert isinstance(body, list)
    assert body, "predictor catalog should not be empty"

    for row in body:
        assert set(row) >= {"id", "name", "view_type"}
        assert isinstance(row["id"], str)
        assert isinstance(row["name"], str)
        assert isinstance(row["view_type"], str)

    predictor_ids = {row["id"] for row in body}
    assert {"resnet50-sc-v1", "resnet50-sc-v1", "resnet50-sc-v1", "resnet50-sc-v1", "yolo-sc-v1", "clip-zero-shot-v1"} <= predictor_ids
