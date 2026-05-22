# pyright: reportMissingImports=false

"""Tests for Label Studio dataset hooks.

Covers strict LS-always-on dataset creation (LS project is mandatory).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.modules.datasets.api.deps import get_label_studio_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DS_PAYLOAD = {
    "name": "test-dataset-ls",
    "task_spec": {"task_type": "classification", "label_space": ["cat", "dog"]},
}


def _override_ls(mock_ls: MagicMock) -> None:
    app.dependency_overrides[get_label_studio_client] = lambda: mock_ls


def _reset() -> None:
    app.dependency_overrides.pop(get_label_studio_client, None)


def test_create_dataset_creates_ls_project() -> None:
    """Creating a dataset should create and persist an LS project, and include ls_project_url."""
    mock_ls = MagicMock()
    mock_ls.create_project = AsyncMock(return_value={"id": 42, "title": "test-dataset-ls"})

    _override_ls(mock_ls)
    try:
        with TestClient(app) as c:
            r = c.post("/api/v1/datasets", json=_DS_PAYLOAD)
        assert r.status_code == 200
        body = r.json()
        assert body["ls_project_id"] == "42"
        assert body["ls_project_url"] == "http://localhost:8080/projects/42"
        mock_ls.create_project.assert_called_once()
    finally:
        _reset()


def test_create_dataset_fails_when_ls_fails() -> None:
    """Creating a dataset should return 502 when LS creation fails."""
    mock_ls = MagicMock()
    mock_ls.create_project = AsyncMock(side_effect=RuntimeError("LS down"))

    _override_ls(mock_ls)
    try:
        with TestClient(app) as c:
            r = c.post("/api/v1/datasets", json=_DS_PAYLOAD)
        assert r.status_code == 502
    finally:
        _reset()
