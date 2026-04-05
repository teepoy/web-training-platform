"""Integration tests for Label Studio prediction sync endpoint.

Tests use the same pattern as test_ls_annotation_sync.py — real SQLite-backed
TestClient for the repository layer, but mock out `container.label_studio_client()`
and `container.config()` so no real Label Studio server is required.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(enabled: bool = False) -> MagicMock:
    cfg = MagicMock()
    cfg.label_studio.enabled = enabled
    cfg.label_studio.url = "http://fake-ls:8080"
    cfg.label_studio.api_key = "fake-key"
    return cfg


def _make_ls_client() -> AsyncMock:
    client = AsyncMock()
    client.import_predictions = AsyncMock(return_value={"count": 1})
    return client


def _make_dataset(ls_project_id: str | None = "42") -> "Dataset":
    from app.domain.models import Dataset
    return Dataset(
        id=str(uuid4()),
        name="pred-sync-ds",
        ls_project_id=ls_project_id,
    )


def _make_sample(dataset_id: str, ls_task_id: int | None = 10) -> "Sample":
    from app.domain.models import Sample
    return Sample(
        id=str(uuid4()),
        dataset_id=dataset_id,
        image_uris=[],
        ls_task_id=ls_task_id,
    )


def _make_prediction(sample_id: str) -> "PredictionResult":
    from app.domain.models import PredictionResult
    return PredictionResult(
        id=str(uuid4()),
        sample_id=sample_id,
        predicted_label="cat",
        score=0.9,
        model_artifact_id="artifact-123",
    )


# ---------------------------------------------------------------------------
# Test 1: sync_predictions_ls_disabled — LS not enabled, returns error message
# ---------------------------------------------------------------------------


def test_sync_predictions_ls_disabled() -> None:
    """When LS is disabled, sync returns synced_count=0 with an error message."""
    mock_config = _make_config(enabled=False)

    import app.main as main_module

    dataset = _make_dataset(ls_project_id=None)
    repo_mock = AsyncMock()
    repo_mock.get_dataset = AsyncMock(return_value=dataset)

    with TestClient(app) as c:
        with patch.object(main_module.container, "config", return_value=mock_config):
            with patch.object(main_module.container, "repository", return_value=repo_mock):
                r = c.post(f"/api/v1/datasets/{dataset.id}/sync-predictions-to-ls")

    assert r.status_code == 200
    body = r.json()
    assert body["synced_count"] == 0
    assert body["skipped_count"] == 0
    assert len(body["errors"]) == 1
    assert "not enabled" in body["errors"][0].lower() or "not linked" in body["errors"][0].lower()


# ---------------------------------------------------------------------------
# Test 2: sync_predictions_ls_enabled — happy path, synced_count matches
# ---------------------------------------------------------------------------


def test_sync_predictions_ls_enabled() -> None:
    """Create dataset+samples+predictions and call sync; verify synced_count."""
    mock_config = _make_config(enabled=True)
    mock_ls_client = _make_ls_client()

    import app.main as main_module

    dataset = _make_dataset(ls_project_id="55")
    sample = _make_sample(dataset.id, ls_task_id=10)
    prediction = _make_prediction(sample.id)

    repo_mock = AsyncMock()
    repo_mock.get_dataset = AsyncMock(return_value=dataset)
    repo_mock.list_predictions_for_dataset = AsyncMock(return_value=[prediction])
    repo_mock.list_samples = AsyncMock(return_value=([sample], 1))

    with TestClient(app) as c:
        with patch.object(main_module.container, "config", return_value=mock_config):
            with patch.object(main_module.container, "label_studio_client", return_value=mock_ls_client):
                with patch.object(main_module.container, "repository", return_value=repo_mock):
                    r = c.post(f"/api/v1/datasets/{dataset.id}/sync-predictions-to-ls")

    assert r.status_code == 200
    body = r.json()
    assert body["synced_count"] == 1
    assert body["skipped_count"] == 0
    assert body["errors"] == []

    # LS import_predictions must have been called with the right project_id
    mock_ls_client.import_predictions.assert_called_once()
    call_args = mock_ls_client.import_predictions.call_args
    assert call_args[0][0] == 55  # project_id as int
    batch = call_args[0][1]
    assert len(batch) == 1
    assert batch[0]["task"] == 10
    assert batch[0]["score"] == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# Test 3: sync_predictions_no_ls_project — dataset without ls_project_id
# ---------------------------------------------------------------------------


def test_sync_predictions_no_ls_project() -> None:
    """Dataset without ls_project_id returns synced_count=0 with error."""
    mock_config = _make_config(enabled=True)

    import app.main as main_module

    dataset = _make_dataset(ls_project_id=None)
    repo_mock = AsyncMock()
    repo_mock.get_dataset = AsyncMock(return_value=dataset)

    with TestClient(app) as c:
        with patch.object(main_module.container, "config", return_value=mock_config):
            with patch.object(main_module.container, "repository", return_value=repo_mock):
                r = c.post(f"/api/v1/datasets/{dataset.id}/sync-predictions-to-ls")

    assert r.status_code == 200
    body = r.json()
    assert body["synced_count"] == 0
    assert len(body["errors"]) == 1


# ---------------------------------------------------------------------------
# Test 4: sync_predictions_dataset_not_found — 404 when dataset missing
# ---------------------------------------------------------------------------


def test_sync_predictions_dataset_not_found() -> None:
    """When dataset does not exist, sync returns 404."""
    import app.main as main_module

    repo_mock = AsyncMock()
    repo_mock.get_dataset = AsyncMock(return_value=None)

    with TestClient(app) as c:
        with patch.object(main_module.container, "repository", return_value=repo_mock):
            r = c.post("/api/v1/datasets/nonexistent-id/sync-predictions-to-ls")

    assert r.status_code == 404
    assert r.json()["detail"] == "Dataset not found"


# ---------------------------------------------------------------------------
# Test 5: sync_predictions_skips_unlinked_samples — no ls_task_id → skipped
# ---------------------------------------------------------------------------


def test_sync_predictions_skips_unlinked_samples() -> None:
    """Samples without ls_task_id are counted as skipped, not synced."""
    mock_config = _make_config(enabled=True)
    mock_ls_client = _make_ls_client()

    import app.main as main_module

    dataset = _make_dataset(ls_project_id="77")
    # Two samples: one with ls_task_id, one without
    sample_linked = _make_sample(dataset.id, ls_task_id=20)
    sample_unlinked = _make_sample(dataset.id, ls_task_id=None)

    pred_linked = _make_prediction(sample_linked.id)
    pred_unlinked = _make_prediction(sample_unlinked.id)

    repo_mock = AsyncMock()
    repo_mock.get_dataset = AsyncMock(return_value=dataset)
    repo_mock.list_predictions_for_dataset = AsyncMock(return_value=[pred_linked, pred_unlinked])
    repo_mock.list_samples = AsyncMock(return_value=([sample_linked, sample_unlinked], 2))

    with TestClient(app) as c:
        with patch.object(main_module.container, "config", return_value=mock_config):
            with patch.object(main_module.container, "label_studio_client", return_value=mock_ls_client):
                with patch.object(main_module.container, "repository", return_value=repo_mock):
                    r = c.post(f"/api/v1/datasets/{dataset.id}/sync-predictions-to-ls")

    assert r.status_code == 200
    body = r.json()
    assert body["synced_count"] == 1
    assert body["skipped_count"] == 1
    assert body["errors"] == []

    # LS import should only receive 1 prediction (the linked one)
    mock_ls_client.import_predictions.assert_called_once()
    batch = mock_ls_client.import_predictions.call_args[0][1]
    assert len(batch) == 1
    assert batch[0]["task"] == 20
