# pyright: reportMissingImports=false

"""Tests for Label Studio dataset hooks.

Covers strict LS-always-on dataset creation and link-ls persistence.
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
    """Creating a dataset should create and persist an LS project."""
    mock_ls = MagicMock()
    mock_ls.create_project = AsyncMock(return_value={"id": 42, "title": "test-dataset-ls"})

    _override_ls(mock_ls)
    try:
        with TestClient(app) as c:
            r = c.post("/api/v1/datasets", json=_DS_PAYLOAD)
        assert r.status_code == 200
        body = r.json()
        assert body["ls_project_id"] == "42"
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


# ---------------------------------------------------------------------------
# test_link_ls_project
# ---------------------------------------------------------------------------


def test_link_ls_project() -> None:
    """POST /api/v1/datasets/{id}/link-ls should persist the ls_project_id."""
    mock_ls = MagicMock()
    mock_ls.create_project = AsyncMock(return_value={"id": 42, "title": "test-dataset-ls"})

    _override_ls(mock_ls)
    try:
        with TestClient(app) as c:
            r = c.post("/api/v1/datasets", json=_DS_PAYLOAD)
            assert r.status_code == 200
            body = r.json()
            assert body["ls_project_id"] == "42"
            dataset_id = body["id"]

            r2 = c.post(f"/api/v1/datasets/{dataset_id}/link-ls", json={"ls_project_id": "99"})
            assert r2.status_code == 200
            assert r2.json()["ls_project_id"] == "99"

            r3 = c.get(f"/api/v1/datasets/{dataset_id}")
            assert r3.status_code == 200
            assert r3.json()["ls_project_id"] == "99"
    finally:
        _reset()


# ---------------------------------------------------------------------------
# test_link_ls_project_not_found
# ---------------------------------------------------------------------------


def test_link_ls_project_not_found() -> None:
    """POST /api/v1/datasets/{id}/link-ls should return 404 for nonexistent dataset."""
    mock_ls = MagicMock()
    mock_ls.create_project = AsyncMock(return_value={"id": 42, "title": "test-dataset-ls"})

    _override_ls(mock_ls)
    try:
        with TestClient(app) as c:
            r = c.post(
                "/api/v1/datasets/nonexistent-dataset-id-xyz/link-ls",
                json={"ls_project_id": "1"},
            )
    finally:
        _reset()
    assert r.status_code == 404
