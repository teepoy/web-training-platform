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

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.modules.datasets.domain.sample_row import SampleRow
from app.modules.datasets.port.http.deps import (
    get_dataset_storage_factory,
    get_label_studio_client,
)
from app.modules.datasets.port.http.deps import get_repository
from app.shared.api.schemas import DatasetStorageMode

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


def _clear_overrides() -> None:
    for dep in (
        get_repository,
        get_label_studio_client,
        get_dataset_storage_factory,
    ):
        app.dependency_overrides.pop(dep, None)


def _make_storage_factory(mock_storage: AsyncMock) -> AsyncMock:
    """Return a mock DatasetStorageFactory whose open() returns mock_storage."""
    factory_mock = AsyncMock()
    factory_mock.open = AsyncMock(return_value=mock_storage)
    return factory_mock


# ---------------------------------------------------------------------------
# Test 1: create_annotation — sample with ls_task_id, LS sync succeeds
# ---------------------------------------------------------------------------


def test_create_annotation_with_task_id() -> None:
    """When sample has ls_task_id, annotation creates and syncs to LS."""
    mock_ls_client = _make_ls_client()
    from app.shared.api.schemas import Annotation, Dataset, TaskSpec, Sample
    from datetime import datetime, UTC
    from uuid import uuid4

    sample_id = str(uuid4())
    dataset_id = str(uuid4())

    sample_with_task = SampleRow(
        sample_id=sample_id,
        dataset_id=dataset_id,
        ls_task_id=42,
    )

    repo_mock = AsyncMock()
    repo_mock.get_sample = AsyncMock()
    repo_mock.create_annotation = AsyncMock()
    repo_mock.get_dataset = AsyncMock(return_value=Dataset(
        id=dataset_id,
        name="test-dataset",
        task_spec=TaskSpec(task_type="classification", label_space=["cat", "dog"]),
    ))
    repo_mock.update_dataset_meta = AsyncMock()

    created_ann = Annotation(
        id=str(uuid4()),
        sample_id=sample_id,
        label="cat",
        created_by="tester",
        created_at=datetime.now(UTC),
    )

    storage_mock = AsyncMock()
    storage_mock.get_sample = AsyncMock(return_value=sample_with_task)
    storage_mock.create_annotations = AsyncMock(return_value=1)

    with TestClient(app) as c:
        app.dependency_overrides[get_label_studio_client] = lambda: mock_ls_client
        app.dependency_overrides[get_repository] = lambda: repo_mock
        app.dependency_overrides[get_dataset_storage_factory] = lambda: _make_storage_factory(storage_mock)
        r = c.post(
            "/api/v1/annotations",
            json={"dataset_id": dataset_id, "sample_id": sample_id, "label": "cat", "created_by": "tester"},
        )
        _clear_overrides()

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
    from app.shared.api.schemas import Sample, Dataset, TaskSpec
    from uuid import uuid4

    sample_id = str(uuid4())
    ds_id = str(uuid4())

    repo_mock = AsyncMock()
    repo_mock.get_sample = AsyncMock()
    repo_mock.get_dataset = AsyncMock(return_value=Dataset(
        id=ds_id,
        name="test-dataset",
        task_spec=TaskSpec(task_type="classification", label_space=["cat", "dog"]),
    ))

    storage_mock = AsyncMock()
    storage_mock.get_sample = AsyncMock(return_value=SampleRow(
        sample_id=sample_id,
        dataset_id=ds_id,
        ls_task_id=None,
    ))

    with TestClient(app) as c:
        app.dependency_overrides[get_repository] = lambda: repo_mock
        app.dependency_overrides[get_dataset_storage_factory] = lambda: _make_storage_factory(storage_mock)
        r = c.post(
            "/api/v1/annotations",
            json={"dataset_id": ds_id, "sample_id": sample_id, "label": "dog", "created_by": "tester"},
        )
        _clear_overrides()

    assert r.status_code == 500
    assert "no Label Studio task" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Test 3: sync-annotations-to-ls — happy path
# ---------------------------------------------------------------------------


def test_sync_annotations_to_ls() -> None:
    """Create annotations then call sync endpoint; verify synced_count matches."""
    mock_ls_client = _make_ls_client()
    from app.shared.api.schemas import Annotation, Dataset, Sample
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
    mock_ann = Annotation(
        id=ann_id,
        sample_id=sample_id,
        label="cat",
        created_by="tester",
        created_at=datetime.now(UTC),
    )

    repo_mock = AsyncMock()
    repo_mock.get_dataset = AsyncMock(return_value=mock_dataset)

    sample_row_with_ls = SampleRow(
        sample_id=sample_id,
        dataset_id=dataset_id,
        ls_task_id=10,
    )
    annotated_row = SampleRow(
        sample_id=sample_id,
        dataset_id=dataset_id,
        ls_task_id=10,
        latest_label="cat",
    )

    storage_mock = AsyncMock()
    storage_mock.list_samples = AsyncMock(
        side_effect=lambda limit=50, **kwargs: (
            ([sample_row_with_ls], 1)
            if not kwargs.get("with_labels")
            else ([annotated_row], 1)
        )
    )

    with TestClient(app) as c:
        app.dependency_overrides[get_label_studio_client] = lambda: mock_ls_client
        app.dependency_overrides[get_repository] = lambda: repo_mock
        app.dependency_overrides[get_dataset_storage_factory] = lambda: _make_storage_factory(storage_mock)
        r = c.post(f"/api/v1/datasets/{dataset_id}/sync-annotations-to-ls")
        _clear_overrides()

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
    from app.shared.api.schemas import Dataset
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
        app.dependency_overrides[get_repository] = lambda: repo_mock
        r = c.post(f"/api/v1/datasets/{dataset_id}/sync-annotations-to-ls")
        _clear_overrides()

    assert r.status_code == 500
    assert "no Label Studio project" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Test 5: sync-annotations-to-ls — dataset not found
# ---------------------------------------------------------------------------


def test_sync_annotations_dataset_not_found() -> None:
    """When dataset does not exist, sync returns 404."""
    repo_mock = AsyncMock()
    repo_mock.get_dataset = AsyncMock(return_value=None)

    with TestClient(app) as c:
        app.dependency_overrides[get_repository] = lambda: repo_mock
        r = c.post("/api/v1/datasets/nonexistent-dataset-id/sync-annotations-to-ls")
        _clear_overrides()

    assert r.status_code == 404
