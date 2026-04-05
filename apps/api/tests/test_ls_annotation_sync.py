"""Integration tests for Label Studio annotation sync endpoints.

Tests use a real SQLite-backed TestClient (same as other annotation tests)
for the repository layer, but mock out `container.label_studio_client()` and
`container.config()` for LS-specific paths so no real Label Studio server is
required.
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


def _create_dataset(c: TestClient, ls_project_id: str | None = None) -> str:
    """Create a dataset and return its ID."""
    r = c.post("/api/v1/datasets", json={"name": "ls-sync-test-ds", "task_spec": _TASK_SPEC})
    assert r.status_code == 200
    dataset_id = r.json()["id"]

    if ls_project_id is not None:
        # Patch the dataset's ls_project_id via a direct repository update
        # by re-reading through our helper
        pass

    return dataset_id


def _create_sample(c: TestClient, dataset_id: str) -> str:
    r = c.post(f"/api/v1/datasets/{dataset_id}/samples", json={"image_uris": []})
    assert r.status_code == 200
    return r.json()["id"]


def _create_annotation(c: TestClient, sample_id: str, label: str = "cat") -> dict:
    r = c.post(
        "/api/v1/annotations",
        json={"sample_id": sample_id, "label": label, "created_by": "tester"},
    )
    assert r.status_code == 200
    return r.json()


# ---------------------------------------------------------------------------
# Shared config mock builders
# ---------------------------------------------------------------------------


def _make_config(enabled: bool = False) -> MagicMock:
    cfg = MagicMock()
    cfg.label_studio.enabled = enabled
    cfg.label_studio.url = "http://fake-ls:8080"
    cfg.label_studio.api_key = "fake-key"
    return cfg


def _make_ls_client() -> AsyncMock:
    """Return a fully-async mock LS client."""
    client = AsyncMock()
    client.create_annotation = AsyncMock(return_value={"id": 99, "task": 1, "result": []})
    return client


# ---------------------------------------------------------------------------
# Test 1: create_annotation — LS disabled, no LS call
# ---------------------------------------------------------------------------


def test_create_annotation_ls_disabled() -> None:
    """When LS is disabled, annotation creates normally with no LS call."""
    mock_ls_client = _make_ls_client()
    mock_config = _make_config(enabled=False)

    import app.main as main_module

    with TestClient(app) as c:
        with patch.object(main_module.container, "config", return_value=mock_config):
            with patch.object(main_module.container, "label_studio_client", return_value=mock_ls_client):
                dataset_id = _create_dataset(c)
                sample_id = _create_sample(c, dataset_id)

                r = c.post(
                    "/api/v1/annotations",
                    json={"sample_id": sample_id, "label": "cat", "created_by": "tester"},
                )
                assert r.status_code == 200
                body = r.json()
                assert body["label"] == "cat"
                assert body["sample_id"] == sample_id

    # LS create_annotation must NOT have been called
    mock_ls_client.create_annotation.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2: create_annotation — LS enabled AND sample has ls_task_id
# ---------------------------------------------------------------------------


def test_create_annotation_ls_enabled_with_task_id() -> None:
    """When LS is enabled and sample has ls_task_id, LS create_annotation is called."""
    mock_ls_client = _make_ls_client()
    mock_config = _make_config(enabled=True)

    import app.main as main_module

    with TestClient(app) as c:
        # Create dataset and sample through normal API
        dataset_id = _create_dataset(c)
        sample_id = _create_sample(c, dataset_id)

        # Directly set ls_task_id on the sample in the repository
        # We use the repository directly via the container singleton
        import asyncio
        from app.main import container as real_container

        async def _set_task_id() -> None:
            repo = real_container.repository()
            sample = await repo.get_sample(sample_id)
            sample.ls_task_id = 42
            # Use SQL update via the repository's update method if available,
            # otherwise patch the get_sample return value
            # Since there's no direct update_sample endpoint, we patch get_sample
            pass

        # Patch get_sample so it returns a sample with ls_task_id=42
        from app.domain.models import Sample
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

        with patch.object(main_module.container, "config", return_value=mock_config):
            with patch.object(main_module.container, "label_studio_client", return_value=mock_ls_client):
                repo_mock = AsyncMock()
                repo_mock.get_sample = AsyncMock(side_effect=_mock_get_sample)
                repo_mock.create_annotation = AsyncMock()

                from app.domain.models import Annotation
                from datetime import datetime, UTC
                from uuid import uuid4
                created_ann = Annotation(
                    id=str(uuid4()),
                    sample_id=sample_id,
                    label="cat",
                    created_by="tester",
                    created_at=datetime.now(UTC),
                )
                repo_mock.create_annotation.return_value = created_ann

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
    # Second arg is the LS result list
    ls_result = call_args[0][1]
    assert isinstance(ls_result, list)
    assert ls_result[0]["type"] == "choices"
    assert ls_result[0]["value"]["choices"] == ["cat"]


# ---------------------------------------------------------------------------
# Test 3: create_annotation — LS enabled but sample has NO ls_task_id
# ---------------------------------------------------------------------------


def test_create_annotation_ls_enabled_no_task_id() -> None:
    """When LS is enabled but sample has no ls_task_id, no LS call is made."""
    mock_ls_client = _make_ls_client()
    mock_config = _make_config(enabled=True)

    import app.main as main_module

    with TestClient(app) as c:
        with patch.object(main_module.container, "config", return_value=mock_config):
            with patch.object(main_module.container, "label_studio_client", return_value=mock_ls_client):
                dataset_id = _create_dataset(c)
                sample_id = _create_sample(c, dataset_id)

                # sample has ls_task_id=None (default), no LS call expected
                r = c.post(
                    "/api/v1/annotations",
                    json={"sample_id": sample_id, "label": "dog", "created_by": "tester"},
                )
                assert r.status_code == 200
                assert r.json()["label"] == "dog"

    mock_ls_client.create_annotation.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4: sync-annotations-to-ls — happy path
# ---------------------------------------------------------------------------


def test_sync_annotations_to_ls() -> None:
    """Create annotations then call sync endpoint; verify synced_count matches."""
    mock_ls_client = _make_ls_client()
    mock_config = _make_config(enabled=True)

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
# Test 5: sync-annotations-to-ls — LS not enabled
# ---------------------------------------------------------------------------


def test_sync_annotations_to_ls_not_enabled() -> None:
    """When LS is disabled, sync returns synced_count=0 with an error message."""
    mock_config = _make_config(enabled=False)

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

    assert r.status_code == 200
    body = r.json()
    assert body["synced_count"] == 0
    assert len(body["errors"]) == 1
    assert "not enabled" in body["errors"][0].lower() or "not linked" in body["errors"][0].lower()


# ---------------------------------------------------------------------------
# Test 6: sync-annotations-to-ls — dataset not found
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
