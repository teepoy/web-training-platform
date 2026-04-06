"""Integration tests for Label Studio annotation sync endpoints.

Tests use a real SQLite-backed TestClient (same as other annotation tests)
for the repository layer, but mock out ``container.label_studio_client()`` and
``container.config()`` for LS-specific paths so no real Label Studio server is
required.

With strict LS enforcement:
- LS is always on (no ``enabled`` flag).
- ``create_annotation`` fails 500 if sample has no ``ls_task_id``.
- ``sync-annotations-to-ls`` fails 500 if dataset has no ``ls_project_id``.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TASK_SPEC = {"task_type": "classification", "label_space": ["cat", "dog"]}


def _make_config() -> MagicMock:
    cfg = MagicMock()
    cfg.label_studio.url = "http://fake-ls:8080"
    cfg.label_studio.api_key = "fake-key"
    cfg.label_studio.database_url = "postgresql+asyncpg://fake"
    return cfg


def _make_ls_client() -> AsyncMock:
    """Return a fully-async mock LS client."""
    client = AsyncMock()
    client.create_annotation = AsyncMock(return_value={"id": 99, "task": 1, "result": []})
    return client


# ---------------------------------------------------------------------------
# Test 1: create_annotation — sample with ls_task_id, LS sync succeeds
# ---------------------------------------------------------------------------


def test_create_annotation_with_task_id() -> None:
    """When sample has ls_task_id, annotation creates and syncs to LS."""
    mock_ls_client = _make_ls_client()
    mock_config = _make_config()

    import app.main as main_module
    from app.domain.models import Annotation, Sample
    from datetime import datetime, UTC
    from uuid import uuid4

    sample_id = str(uuid4())
    dataset_id = str(uuid4())

    sample_with_task = Sample(
        id=sample_id,
        dataset_id=dataset_id,
        image_uris=[],
        metadata={},
        ls_task_id=42,
    )

    async def _mock_get_sample(sid: str):
        if sid == sample_id:
            return sample_with_task
        return None

    repo_mock = AsyncMock()
    repo_mock.get_sample = AsyncMock(side_effect=_mock_get_sample)
    repo_mock.create_annotation = AsyncMock()

    created_ann = Annotation(
        id=str(uuid4()),
        sample_id=sample_id,
        label="cat",
        created_by="tester",
        created_at=datetime.now(UTC),
    )
    repo_mock.create_annotation.return_value = created_ann

    with TestClient(app) as c:
        with patch.object(main_module.container, "config", return_value=mock_config):
            with patch.object(main_module.container, "label_studio_client", return_value=mock_ls_client):
                with patch.object(main_module.container, "repository", return_value=repo_mock):
                    r = c.post(
                        "/api/v1/annotations",
                        json={"sample_id": sample_id, "label": "cat", "created_by": "tester"},
                    )

    assert r.status_code == 200
    assert r.json()["label"] == "cat"

    # LS create_annotation MUST have been called with task_id=42
    mock_ls_client.create_annotation.assert_called_once()
    call_args = mock_ls_client.create_annotation.call_args
    assert call_args[0][0] == 42  # task_id positional arg
    ls_result = call_args[0][1]
    assert isinstance(ls_result, list)
    assert ls_result[0]["type"] == "choices"
    assert ls_result[0]["value"]["choices"] == ["cat"]


# ---------------------------------------------------------------------------
# Test 2: create_annotation — sample with NO ls_task_id → 500
# ---------------------------------------------------------------------------


def test_create_annotation_no_task_id_returns_500() -> None:
    """When sample has no ls_task_id, annotation creation returns 500."""
    mock_config = _make_config()

    import app.main as main_module
    from app.domain.models import Sample
    from uuid import uuid4

    sample_id = str(uuid4())
    sample_no_task = Sample(
        id=sample_id,
        dataset_id=str(uuid4()),
        image_uris=[],
        metadata={},
        ls_task_id=None,
    )

    repo_mock = AsyncMock()
    repo_mock.get_sample = AsyncMock(return_value=sample_no_task)

    with TestClient(app) as c:
        with patch.object(main_module.container, "config", return_value=mock_config):
            with patch.object(main_module.container, "repository", return_value=repo_mock):
                r = c.post(
                    "/api/v1/annotations",
                    json={"sample_id": sample_id, "label": "dog", "created_by": "tester"},
                )

    assert r.status_code == 500
    assert "no Label Studio task" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Test 3: sync-annotations-to-ls — happy path
# ---------------------------------------------------------------------------


def test_sync_annotations_to_ls() -> None:
    """Create annotations then call sync endpoint; verify synced_count matches."""
    mock_ls_client = _make_ls_client()
    mock_config = _make_config()

    import app.main as main_module
    from app.domain.models import Annotation, Dataset, Sample
    from datetime import datetime, UTC
    from uuid import uuid4

    dataset_id = str(uuid4())
    sample_id = str(uuid4())
    ann_id = str(uuid4())

    mock_dataset = Dataset(
        id=dataset_id,
        name="sync-test-ds",
        ls_project_id="55",
    )
    mock_sample = Sample(
        id=sample_id,
        dataset_id=dataset_id,
        image_uris=[],
        ls_task_id=10,
    )
    mock_ann = Annotation(
        id=ann_id,
        sample_id=sample_id,
        label="cat",
        created_by="tester",
        created_at=datetime.now(UTC),
    )

    repo_mock = AsyncMock()
    repo_mock.get_dataset = AsyncMock(return_value=mock_dataset)
    repo_mock.list_samples = AsyncMock(return_value=([mock_sample], 1))
    repo_mock.list_annotations_for_dataset = AsyncMock(return_value=[mock_ann])

    with TestClient(app) as c:
        with patch.object(main_module.container, "config", return_value=mock_config):
            with patch.object(main_module.container, "label_studio_client", return_value=mock_ls_client):
                with patch.object(main_module.container, "repository", return_value=repo_mock):
                    r = c.post(f"/api/v1/datasets/{dataset_id}/sync-annotations-to-ls")

    assert r.status_code == 200
    body = r.json()
    assert body["synced_count"] == 1
    assert body["errors"] == []

    mock_ls_client.create_annotation.assert_called_once()
    call_args = mock_ls_client.create_annotation.call_args
    assert call_args[0][0] == 10  # ls_task_id


# ---------------------------------------------------------------------------
# Test 4: sync-annotations-to-ls — no ls_project_id → 500
# ---------------------------------------------------------------------------


def test_sync_annotations_no_project_returns_500() -> None:
    """When dataset has no ls_project_id, sync returns 500."""
    mock_config = _make_config()

    import app.main as main_module
    from app.domain.models import Dataset
    from uuid import uuid4

    dataset_id = str(uuid4())
    mock_dataset = Dataset(
        id=dataset_id,
        name="not-linked-ds",
        ls_project_id=None,
    )

    repo_mock = AsyncMock()
    repo_mock.get_dataset = AsyncMock(return_value=mock_dataset)

    with TestClient(app) as c:
        with patch.object(main_module.container, "config", return_value=mock_config):
            with patch.object(main_module.container, "repository", return_value=repo_mock):
                r = c.post(f"/api/v1/datasets/{dataset_id}/sync-annotations-to-ls")

    assert r.status_code == 500
    assert "no Label Studio project" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Test 5: sync-annotations-to-ls — dataset not found
# ---------------------------------------------------------------------------


def test_sync_annotations_dataset_not_found() -> None:
    """When dataset does not exist, sync returns 404."""
    import app.main as main_module

    repo_mock = AsyncMock()
    repo_mock.get_dataset = AsyncMock(return_value=None)

    with TestClient(app) as c:
        with patch.object(main_module.container, "repository", return_value=repo_mock):
            r = c.post("/api/v1/datasets/nonexistent-dataset-id/sync-annotations-to-ls")

    assert r.status_code == 404
    assert r.json()["detail"] == "Dataset not found"
