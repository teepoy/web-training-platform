"""Tests for Label Studio sample hooks (T6).

Tests the create-sample LS task creation hook and the _make_ls_image_url helper.
Uses dependency_overrides on the Container providers so no real LS server is needed.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app, container, _make_ls_image_url


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DS_PAYLOAD = {
    "name": "sample-test-dataset",
    "task_spec": {"task_type": "classification", "label_space": ["a", "b"]},
}

_SAMPLE_PAYLOAD = {
    "image_uris": ["memory://samples/test.jpg"],
    "metadata": {},
}


def providers_value(val):  # type: ignore[return]
    """Return a dependency-injector compatible provider that always returns val."""
    from dependency_injector import providers

    return providers.Object(val)


def _reset_container_overrides() -> None:
    container.label_studio_client.reset_override()
    container.config.reset_override()


# ---------------------------------------------------------------------------
# test_create_sample_ls_disabled
# ---------------------------------------------------------------------------


def test_create_sample_ls_disabled() -> None:
    """Creating a sample with LS disabled must NOT set ls_task_id."""
    # local-smoke config has label_studio.enabled = false by default
    with TestClient(app) as c:
        ds = c.post("/api/v1/datasets", json=_DS_PAYLOAD)
        assert ds.status_code == 200
        dataset_id = ds.json()["id"]

        r = c.post(f"/api/v1/datasets/{dataset_id}/samples", json=_SAMPLE_PAYLOAD)
    assert r.status_code == 200
    assert r.json()["ls_task_id"] is None


# ---------------------------------------------------------------------------
# test_create_sample_ls_enabled_with_project
# ---------------------------------------------------------------------------


def test_create_sample_ls_enabled_with_project() -> None:
    """Creating a sample with LS enabled and dataset linked should set ls_task_id."""
    mock_cfg = MagicMock()
    mock_cfg.db.auto_create = True
    mock_cfg.label_studio.enabled = True

    mock_ls = MagicMock()
    mock_ls.create_project = AsyncMock(return_value={"id": 7, "title": "sample-test-dataset"})
    mock_ls.create_task = AsyncMock(return_value={"id": 55})

    container.config.override(providers_value(mock_cfg))
    container.label_studio_client.override(providers_value(mock_ls))

    try:
        with TestClient(app) as c:
            # Dataset creation will call create_project and set ls_project_id = "7"
            ds = c.post("/api/v1/datasets", json=_DS_PAYLOAD)
            assert ds.status_code == 200
            dataset_id = ds.json()["id"]
            assert ds.json()["ls_project_id"] == "7"

            # Sample creation should call create_task
            r = c.post(f"/api/v1/datasets/{dataset_id}/samples", json=_SAMPLE_PAYLOAD)
        assert r.status_code == 200
        body = r.json()
        assert body["ls_task_id"] == 55
        mock_ls.create_task.assert_called_once_with(7, {"image": "/api/v1/images/resolve?uri=memory%3A%2F%2Fsamples%2Ftest.jpg"})
    finally:
        _reset_container_overrides()


# ---------------------------------------------------------------------------
# test_create_sample_ls_enabled_no_project
# ---------------------------------------------------------------------------


def test_create_sample_ls_enabled_no_project() -> None:
    """Sample creation with LS enabled but dataset NOT linked should not set ls_task_id."""
    mock_cfg = MagicMock()
    mock_cfg.db.auto_create = True
    mock_cfg.label_studio.enabled = True

    mock_ls = MagicMock()
    mock_ls.create_task = AsyncMock(return_value={"id": 99})
    # create_project returns id=0, which means ls_project_id stored would be "0"
    # We want dataset without ls_project_id — disable LS during dataset creation,
    # then re-enable for sample creation
    container.label_studio_client.override(providers_value(mock_ls))

    # First create dataset with LS disabled so ls_project_id stays None
    with TestClient(app) as c:
        ds = c.post("/api/v1/datasets", json=_DS_PAYLOAD)
        assert ds.status_code == 200
        dataset_id = ds.json()["id"]
        assert ds.json()["ls_project_id"] is None

        # Now override config to enable LS for sample creation
        container.config.override(providers_value(mock_cfg))

        r = c.post(f"/api/v1/datasets/{dataset_id}/samples", json=_SAMPLE_PAYLOAD)

    try:
        assert r.status_code == 200
        # ls_task_id should remain None because dataset has no ls_project_id
        assert r.json()["ls_task_id"] is None
        mock_ls.create_task.assert_not_called()
    finally:
        _reset_container_overrides()


# ---------------------------------------------------------------------------
# test_make_ls_image_url_s3
# ---------------------------------------------------------------------------


def test_make_ls_image_url_s3() -> None:
    """s3:// URIs should be converted to the resolve endpoint."""
    result = _make_ls_image_url("s3://mybucket/path/to/image.jpg")
    assert result.startswith("/api/v1/images/resolve?uri=")
    assert "s3" in result


# ---------------------------------------------------------------------------
# test_make_ls_image_url_memory
# ---------------------------------------------------------------------------


def test_make_ls_image_url_memory() -> None:
    """memory:// URIs should also be converted to the resolve endpoint."""
    result = _make_ls_image_url("memory://samples/test.png")
    assert result.startswith("/api/v1/images/resolve?uri=")
    assert "memory" in result


# ---------------------------------------------------------------------------
# test_make_ls_image_url_data
# ---------------------------------------------------------------------------


def test_make_ls_image_url_data() -> None:
    """data: URIs should pass through unchanged."""
    uri = "data:image/png;base64,abc123"
    assert _make_ls_image_url(uri) == uri


# ---------------------------------------------------------------------------
# test_make_ls_image_url_http
# ---------------------------------------------------------------------------


def test_make_ls_image_url_http() -> None:
    """http:// URIs should pass through unchanged."""
    uri = "http://example.com/image.jpg"
    assert _make_ls_image_url(uri) == uri
