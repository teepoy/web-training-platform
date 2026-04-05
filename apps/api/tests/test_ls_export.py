"""Tests for Label Studio-sourced export endpoints.

Tests cover:
1. Export with LS enabled — data sourced from LS and converted to platform format.
2. Export with LS disabled — original local-data behavior unchanged.
3. Export with LS fallback — LS raises exception, falls back to local data.
4. Export persist with LS enabled — same as #1 but for the persist endpoint.
"""
from __future__ import annotations

from datetime import datetime, UTC
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


def _make_dataset(ls_project_id: str | None = "10") -> "Dataset":
    from app.domain.models import Dataset

    return Dataset(
        id=str(uuid4()),
        name="export-test-ds",
        ls_project_id=ls_project_id,
    )


def _make_sample(dataset_id: str, ls_task_id: int | None = 101) -> "Sample":
    from app.domain.models import Sample

    return Sample(
        id=str(uuid4()),
        dataset_id=dataset_id,
        image_uris=["http://img/1.jpg"],
        ls_task_id=ls_task_id,
    )


def _make_annotation(sample_id: str, label: str = "cat") -> "Annotation":
    from app.domain.models import Annotation

    return Annotation(
        id=str(uuid4()),
        sample_id=sample_id,
        label=label,
        created_by="tester",
        created_at=datetime.now(UTC),
    )


def _ls_task(task_id: int, label: str = "dog") -> dict:
    """Build a minimal LS export task dict."""
    return {
        "id": task_id,
        "data": {"image": "http://img/1.jpg"},
        "annotations": [
            {
                "id": 999,
                "result": [
                    {
                        "from_name": "classification",
                        "to_name": "image",
                        "type": "choices",
                        "value": {"choices": [label]},
                    }
                ],
            }
        ],
    }


# ---------------------------------------------------------------------------
# Test 1: export_with_ls_enabled
# ---------------------------------------------------------------------------


def test_export_with_ls_enabled() -> None:
    """When LS is enabled and dataset has ls_project_id, export uses LS data."""
    mock_config = _make_config(enabled=True)
    mock_ls_client = AsyncMock()

    import app.main as main_module

    dataset = _make_dataset(ls_project_id="10")
    sample = _make_sample(dataset.id, ls_task_id=101)
    ls_tasks = [_ls_task(task_id=101, label="dog")]

    mock_ls_client.export_project = AsyncMock(return_value=ls_tasks)

    repo_mock = AsyncMock()
    repo_mock.get_dataset = AsyncMock(return_value=dataset)
    repo_mock.list_samples = AsyncMock(return_value=([sample], 1))
    repo_mock.list_annotations_for_dataset = AsyncMock(return_value=[])

    # Minimal artifacts mock that returns a valid export structure
    artifacts_mock = MagicMock()
    artifacts_mock.build_dataset_export = MagicMock(
        side_effect=lambda dataset, samples, annotations: {
            "format": "hf-datasets-friendly-json",
            "dataset": dataset.model_dump(mode="json"),
            "samples": [s.model_dump(mode="json") for s in samples],
            "annotations": [a.model_dump(mode="json") for a in annotations],
            "artifact_layout": {},
        }
    )

    with TestClient(app) as c:
        with patch.object(main_module.container, "config", return_value=mock_config):
            with patch.object(main_module.container, "label_studio_client", return_value=mock_ls_client):
                with patch.object(main_module.container, "repository", return_value=repo_mock):
                    with patch.object(main_module.container, "artifacts", return_value=artifacts_mock):
                        r = c.get(f"/api/v1/exports/{dataset.id}")

    assert r.status_code == 200
    body = r.json()
    assert body["format"] == "hf-datasets-friendly-json"

    # LS export_project must have been called
    mock_ls_client.export_project.assert_called_once_with(10)

    # Annotation should come from LS (label="dog"), not local data
    assert len(body["annotations"]) == 1
    assert body["annotations"][0]["label"] == "dog"
    assert body["annotations"][0]["created_by"] == "label_studio"

    # Sample should be the platform sample matched by ls_task_id
    assert len(body["samples"]) == 1
    assert body["samples"][0]["id"] == sample.id


# ---------------------------------------------------------------------------
# Test 2: export_with_ls_disabled
# ---------------------------------------------------------------------------


def test_export_with_ls_disabled() -> None:
    """When LS is disabled, export uses local repository data unchanged."""
    mock_config = _make_config(enabled=False)
    mock_ls_client = AsyncMock()
    mock_ls_client.export_project = AsyncMock(return_value=[])

    import app.main as main_module

    dataset = _make_dataset(ls_project_id="10")
    sample = _make_sample(dataset.id, ls_task_id=101)
    local_ann = _make_annotation(sample.id, label="cat")

    repo_mock = AsyncMock()
    repo_mock.get_dataset = AsyncMock(return_value=dataset)
    repo_mock.list_samples = AsyncMock(return_value=([sample], 1))
    repo_mock.list_annotations_for_dataset = AsyncMock(return_value=[local_ann])

    artifacts_mock = MagicMock()
    artifacts_mock.build_dataset_export = MagicMock(
        side_effect=lambda dataset, samples, annotations: {
            "format": "hf-datasets-friendly-json",
            "dataset": dataset.model_dump(mode="json"),
            "samples": [s.model_dump(mode="json") for s in samples],
            "annotations": [a.model_dump(mode="json") for a in annotations],
            "artifact_layout": {},
        }
    )

    with TestClient(app) as c:
        with patch.object(main_module.container, "config", return_value=mock_config):
            with patch.object(main_module.container, "label_studio_client", return_value=mock_ls_client):
                with patch.object(main_module.container, "repository", return_value=repo_mock):
                    with patch.object(main_module.container, "artifacts", return_value=artifacts_mock):
                        r = c.get(f"/api/v1/exports/{dataset.id}")

    assert r.status_code == 200
    body = r.json()

    # LS export_project must NOT have been called
    mock_ls_client.export_project.assert_not_called()

    # Should use local annotation (cat), not LS data
    assert len(body["annotations"]) == 1
    assert body["annotations"][0]["label"] == "cat"


# ---------------------------------------------------------------------------
# Test 3: export_with_ls_fallback
# ---------------------------------------------------------------------------


def test_export_with_ls_fallback() -> None:
    """When LS enabled but export_project raises, falls back to local data."""
    mock_config = _make_config(enabled=True)
    mock_ls_client = AsyncMock()
    mock_ls_client.export_project = AsyncMock(side_effect=RuntimeError("LS connection refused"))

    import app.main as main_module

    dataset = _make_dataset(ls_project_id="10")
    sample = _make_sample(dataset.id, ls_task_id=101)
    local_ann = _make_annotation(sample.id, label="cat")

    repo_mock = AsyncMock()
    repo_mock.get_dataset = AsyncMock(return_value=dataset)
    repo_mock.list_samples = AsyncMock(return_value=([sample], 1))
    repo_mock.list_annotations_for_dataset = AsyncMock(return_value=[local_ann])

    artifacts_mock = MagicMock()
    artifacts_mock.build_dataset_export = MagicMock(
        side_effect=lambda dataset, samples, annotations: {
            "format": "hf-datasets-friendly-json",
            "dataset": dataset.model_dump(mode="json"),
            "samples": [s.model_dump(mode="json") for s in samples],
            "annotations": [a.model_dump(mode="json") for a in annotations],
            "artifact_layout": {},
        }
    )

    with TestClient(app) as c:
        with patch.object(main_module.container, "config", return_value=mock_config):
            with patch.object(main_module.container, "label_studio_client", return_value=mock_ls_client):
                with patch.object(main_module.container, "repository", return_value=repo_mock):
                    with patch.object(main_module.container, "artifacts", return_value=artifacts_mock):
                        r = c.get(f"/api/v1/exports/{dataset.id}")

    assert r.status_code == 200
    body = r.json()

    # LS export_project was attempted
    mock_ls_client.export_project.assert_called_once_with(10)

    # Fell back to local annotation (cat)
    assert len(body["annotations"]) == 1
    assert body["annotations"][0]["label"] == "cat"


# ---------------------------------------------------------------------------
# Test 4: export_persist_with_ls
# ---------------------------------------------------------------------------


def test_export_persist_with_ls() -> None:
    """POST /persist with LS enabled sources data from LS and persists it."""
    mock_config = _make_config(enabled=True)
    mock_ls_client = AsyncMock()

    import app.main as main_module

    dataset = _make_dataset(ls_project_id="20")
    sample = _make_sample(dataset.id, ls_task_id=202)
    ls_tasks = [_ls_task(task_id=202, label="dog")]

    mock_ls_client.export_project = AsyncMock(return_value=ls_tasks)

    repo_mock = AsyncMock()
    repo_mock.get_dataset = AsyncMock(return_value=dataset)
    repo_mock.list_samples = AsyncMock(return_value=([sample], 1))
    repo_mock.list_annotations_for_dataset = AsyncMock(return_value=[])

    artifacts_mock = AsyncMock()
    artifacts_mock.persist_dataset_export = AsyncMock(return_value="memory://exports/test.json")

    with TestClient(app) as c:
        with patch.object(main_module.container, "config", return_value=mock_config):
            with patch.object(main_module.container, "label_studio_client", return_value=mock_ls_client):
                with patch.object(main_module.container, "repository", return_value=repo_mock):
                    with patch.object(main_module.container, "artifacts", return_value=artifacts_mock):
                        r = c.post(f"/api/v1/exports/{dataset.id}/persist")

    assert r.status_code == 200
    body = r.json()
    assert body["uri"] == "memory://exports/test.json"

    # LS was consulted
    mock_ls_client.export_project.assert_called_once_with(20)

    # persist_dataset_export was called — check annotations contain LS label
    artifacts_mock.persist_dataset_export.assert_called_once()
    call_kwargs = artifacts_mock.persist_dataset_export.call_args
    passed_annotations = call_kwargs.kwargs.get("annotations") or call_kwargs[1].get("annotations") or call_kwargs[0][2]
    assert len(passed_annotations) == 1
    assert passed_annotations[0].label == "dog"
    assert passed_annotations[0].created_by == "label_studio"
