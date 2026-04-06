# pyright: reportMissingImports=false

"""Tests for Label Studio dataset hooks.

Covers strict LS-always-on dataset creation (LS project is mandatory).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient
from dependency_injector import providers

from app.main import app, container


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DS_PAYLOAD = {
    "name": "test-dataset-ls",
    "task_spec": {"task_type": "classification", "label_space": ["cat", "dog"]},
}


def _override_ls(mock_ls: MagicMock) -> None:
    container.label_studio_client.override(providers.Object(mock_ls))


def _reset() -> None:
    container.label_studio_client.reset_override()


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
