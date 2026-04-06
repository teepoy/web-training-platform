"""Tests for Label Studio-sourced export endpoints.

Tests cover:
1. Export with LS project — data sourced from LS Postgres via LsReadRepository.
2. Export with no LS project — returns 500 (strict enforcement).
3. Export when LS DB fails — returns 502 (no fallback).
4. Export persist with LS — same as #1 but for the persist endpoint.
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


def _make_config() -> MagicMock:
    cfg = MagicMock()
    cfg.label_studio.url = "http://fake-ls:8080"
    cfg.label_studio.api_key = "fake-key"
    cfg.label_studio.database_url = "postgresql+asyncpg://fake"
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


# ---------------------------------------------------------------------------
# Test 1: export sourced from LS Postgres (LsReadRepository)
# ---------------------------------------------------------------------------


def test_export_with_ls_project() -> None:
    """When dataset has ls_project_id, export uses LsReadRepository to read LS Postgres."""
    mock_config = _make_config()

    import app.main as main_module

    dataset = _make_dataset(ls_project_id="10")
    sample = _make_sample(dataset.id, ls_task_id=101)

    repo_mock = AsyncMock()
    repo_mock.get_dataset = AsyncMock(return_value=dataset)
    repo_mock.list_samples = AsyncMock(return_value=([sample], 1))

    # LsReadRepository mock — returns tasks and annotations from LS Postgres
    ls_read_mock = AsyncMock()
    ls_read_mock.get_tasks_for_project = AsyncMock(return_value=[
        {"id": 101, "data": {"image": "http://img/1.jpg"}},
    ])
    ls_read_mock.get_annotations_for_tasks = AsyncMock(return_value={
        101: [
            {
                "id": 999,
                "result": [
                    {
                        "from_name": "classification",
                        "to_name": "image",
                        "type": "choices",
                        "value": {"choices": ["dog"]},
                    }
                ],
            }
        ],
    })

    # Minimal artifacts mock
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
            with patch.object(main_module.container, "ls_read_repository", return_value=ls_read_mock):
                with patch.object(main_module.container, "repository", return_value=repo_mock):
                    with patch.object(main_module.container, "artifacts", return_value=artifacts_mock):
                        r = c.get(f"/api/v1/exports/{dataset.id}")

    assert r.status_code == 200
    body = r.json()
    assert body["format"] == "hf-datasets-friendly-json"

    # LsReadRepository must have been called
    ls_read_mock.get_tasks_for_project.assert_called_once_with(10)
    ls_read_mock.get_annotations_for_tasks.assert_called_once_with([101])

    # Annotation should come from LS (label="dog"), not local data
    assert len(body["annotations"]) == 1
    assert body["annotations"][0]["label"] == "dog"
    assert body["annotations"][0]["created_by"] == "label_studio"

    # Sample should be the platform sample matched by ls_task_id
    assert len(body["samples"]) == 1
    assert body["samples"][0]["id"] == sample.id


# ---------------------------------------------------------------------------
# Test 2: export with no LS project — returns 500 (strict enforcement)
# ---------------------------------------------------------------------------


def test_export_no_ls_project_returns_500() -> None:
    """When dataset has no ls_project_id, export returns 500."""
    mock_config = _make_config()

    import app.main as main_module

    dataset = _make_dataset(ls_project_id=None)

    repo_mock = AsyncMock()
    repo_mock.get_dataset = AsyncMock(return_value=dataset)

    with TestClient(app) as c:
        with patch.object(main_module.container, "config", return_value=mock_config):
            with patch.object(main_module.container, "repository", return_value=repo_mock):
                r = c.get(f"/api/v1/exports/{dataset.id}")

    assert r.status_code == 500
    assert "no Label Studio project" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Test 3: export when LS DB fails — returns 502 (no fallback)
# ---------------------------------------------------------------------------


def test_export_ls_db_failure_returns_502() -> None:
    """When LsReadRepository raises, export returns 502 with no fallback."""
    mock_config = _make_config()

    import app.main as main_module

    dataset = _make_dataset(ls_project_id="10")
    sample = _make_sample(dataset.id, ls_task_id=101)

    repo_mock = AsyncMock()
    repo_mock.get_dataset = AsyncMock(return_value=dataset)
    repo_mock.list_samples = AsyncMock(return_value=([sample], 1))

    ls_read_mock = AsyncMock()
    ls_read_mock.get_tasks_for_project = AsyncMock(side_effect=RuntimeError("LS DB connection refused"))

    with TestClient(app) as c:
        with patch.object(main_module.container, "config", return_value=mock_config):
            with patch.object(main_module.container, "ls_read_repository", return_value=ls_read_mock):
                with patch.object(main_module.container, "repository", return_value=repo_mock):
                    r = c.get(f"/api/v1/exports/{dataset.id}")

    assert r.status_code == 502
    assert "Label Studio database read failed" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Test 4: export persist with LS
# ---------------------------------------------------------------------------


def test_export_persist_with_ls() -> None:
    """POST /persist with LS project sources data from LS Postgres and persists it."""
    mock_config = _make_config()

    import app.main as main_module

    dataset = _make_dataset(ls_project_id="20")
    sample = _make_sample(dataset.id, ls_task_id=202)

    repo_mock = AsyncMock()
    repo_mock.get_dataset = AsyncMock(return_value=dataset)
    repo_mock.list_samples = AsyncMock(return_value=([sample], 1))

    ls_read_mock = AsyncMock()
    ls_read_mock.get_tasks_for_project = AsyncMock(return_value=[
        {"id": 202, "data": {"image": "http://img/2.jpg"}},
    ])
    ls_read_mock.get_annotations_for_tasks = AsyncMock(return_value={
        202: [
            {
                "id": 888,
                "result": [
                    {
                        "from_name": "classification",
                        "to_name": "image",
                        "type": "choices",
                        "value": {"choices": ["dog"]},
                    }
                ],
            }
        ],
    })

    artifacts_mock = AsyncMock()
    artifacts_mock.persist_dataset_export = AsyncMock(return_value="memory://exports/test.json")

    with TestClient(app) as c:
        with patch.object(main_module.container, "config", return_value=mock_config):
            with patch.object(main_module.container, "ls_read_repository", return_value=ls_read_mock):
                with patch.object(main_module.container, "repository", return_value=repo_mock):
                    with patch.object(main_module.container, "artifacts", return_value=artifacts_mock):
                        r = c.post(f"/api/v1/exports/{dataset.id}/persist")

    assert r.status_code == 200
    body = r.json()
    assert body["uri"] == "memory://exports/test.json"

    # LS Postgres was consulted
    ls_read_mock.get_tasks_for_project.assert_called_once_with(20)

    # persist_dataset_export was called — check annotations contain LS label
    artifacts_mock.persist_dataset_export.assert_called_once()
    call_kwargs = artifacts_mock.persist_dataset_export.call_args
    passed_annotations = call_kwargs.kwargs.get("annotations") or call_kwargs[1].get("annotations") or call_kwargs[0][2]
    assert len(passed_annotations) == 1
    assert passed_annotations[0].label == "dog"
    assert passed_annotations[0].created_by == "label_studio"
