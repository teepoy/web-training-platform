"""Tests for Label Studio dataset hooks (T5).

Tests the create-dataset LS project creation hook and the link-ls endpoint.
Uses dependency_overrides on the Container providers so no real LS server is needed.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app, container


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DS_PAYLOAD = {
    "name": "test-dataset-ls",
    "task_spec": {"task_type": "classification", "label_space": ["cat", "dog"]},
}


def _reset_container_overrides() -> None:
    """Remove any overrides applied during a test."""
    container.label_studio_client.reset_override()
    container.config.reset_override()


# ---------------------------------------------------------------------------
# test_create_dataset_ls_disabled
# ---------------------------------------------------------------------------


def test_create_dataset_ls_disabled() -> None:
    """Creating a dataset with LS disabled must NOT set ls_project_id."""
    # local-smoke config has label_studio.enabled = false by default
    with TestClient(app) as c:
        r = c.post("/api/v1/datasets", json=_DS_PAYLOAD)
    assert r.status_code == 200
    body = r.json()
    assert body["ls_project_id"] is None


# ---------------------------------------------------------------------------
# test_create_dataset_ls_enabled
# ---------------------------------------------------------------------------


def test_create_dataset_ls_enabled() -> None:
    """Creating a dataset with LS enabled should call create_project and store the ID."""
    # Build a mock config that has label_studio.enabled = True
    mock_cfg = MagicMock()
    mock_cfg.db.auto_create = True
    mock_cfg.label_studio.enabled = True

    # Build a mock LS client whose create_project returns project id 42
    mock_ls = MagicMock()
    mock_ls.create_project = AsyncMock(return_value={"id": 42, "title": "test-dataset-ls"})

    container.config.override(providers_value(mock_cfg))
    container.label_studio_client.override(providers_value(mock_ls))

    try:
        with TestClient(app) as c:
            r = c.post("/api/v1/datasets", json=_DS_PAYLOAD)
        assert r.status_code == 200
        body = r.json()
        assert body["ls_project_id"] == "42"
        mock_ls.create_project.assert_called_once()
    finally:
        _reset_container_overrides()


# ---------------------------------------------------------------------------
# test_link_ls_project
# ---------------------------------------------------------------------------


def test_link_ls_project() -> None:
    """POST /api/v1/datasets/{id}/link-ls should persist the ls_project_id."""
    with TestClient(app) as c:
        # Create dataset first
        r = c.post("/api/v1/datasets", json=_DS_PAYLOAD)
        assert r.status_code == 200
        dataset_id = r.json()["id"]
        assert r.json()["ls_project_id"] is None

        # Link it to LS project 99
        r2 = c.post(f"/api/v1/datasets/{dataset_id}/link-ls", json={"ls_project_id": "99"})
        assert r2.status_code == 200
        assert r2.json()["ls_project_id"] == "99"

        # Verify persistence via GET
        r3 = c.get(f"/api/v1/datasets/{dataset_id}")
        assert r3.status_code == 200
        assert r3.json()["ls_project_id"] == "99"


# ---------------------------------------------------------------------------
# test_link_ls_project_not_found
# ---------------------------------------------------------------------------


def test_link_ls_project_not_found() -> None:
    """POST /api/v1/datasets/{id}/link-ls should return 404 for nonexistent dataset."""
    with TestClient(app) as c:
        r = c.post(
            "/api/v1/datasets/nonexistent-dataset-id-xyz/link-ls",
            json={"ls_project_id": "1"},
        )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Internal helper — wraps a plain value in a provider-compatible callable
# ---------------------------------------------------------------------------


def providers_value(val):  # type: ignore[return]
    """Return a dependency-injector compatible provider that always returns val."""
    from dependency_injector import providers

    return providers.Object(val)
