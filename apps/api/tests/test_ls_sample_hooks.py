"""Tests for Label Studio sample hooks.

Tests the create-sample LS task creation hook and the _make_ls_image_url helper.
Uses dependency_overrides on the Container providers so no real LS server is needed.

With strict LS enforcement:
- LS is always on (no ``enabled`` flag).
- ``create_sample`` fails 500 if dataset has no ``ls_project_id``.
- ``create_sample`` fails 502 if LS task creation fails.
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
# test_create_sample_with_project
# ---------------------------------------------------------------------------


def test_create_sample_with_ls_project() -> None:
    """Creating a sample with dataset linked to LS should set ls_task_id."""
    mock_cfg = MagicMock()
    mock_cfg.db.auto_create = True

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
# test_create_sample_no_ls_project_returns_500
# ---------------------------------------------------------------------------


def test_create_sample_no_ls_project_returns_500() -> None:
    """Sample creation on dataset without ls_project_id returns 500."""
    mock_cfg = MagicMock()
    mock_cfg.db.auto_create = True

    # create_project raises so dataset gets no ls_project_id
    mock_ls = MagicMock()
    mock_ls.create_project = AsyncMock(side_effect=RuntimeError("LS down"))
    mock_ls.create_task = AsyncMock(return_value={"id": 99})

    container.config.override(providers_value(mock_cfg))
    container.label_studio_client.override(providers_value(mock_ls))

    try:
        with TestClient(app) as c:
            # Dataset creation will fail at LS project creation → 502
            ds = c.post("/api/v1/datasets", json=_DS_PAYLOAD)
            assert ds.status_code == 502  # strict enforcement

            # We need a dataset without ls_project_id. Use link-ls to create one,
            # or create with a mock that returns a dataset without ls_project_id.
            # Reset config to something that won't fail at dataset creation level
            _reset_container_overrides()

            # Create dataset without LS by patching container to have a no-op LS client for creation
            # Actually, the simplest approach: create dataset normally then test sample creation
            # against a dataset that has no ls_project_id by using the link-ls endpoint to clear it.
            # Better: just use the real local-smoke config which doesn't have LS enforcement
            # Wait — with strict enforcement, create_dataset ALWAYS creates LS project.
            # So we need to mock get_dataset to return a dataset without ls_project_id.
            pass

        # Use mocked repository to test the sample creation path
        from app.domain.models import Dataset, Sample
        from uuid import uuid4
        from unittest.mock import patch

        import app.main as main_module

        dataset_no_project = Dataset(
            id=str(uuid4()),
            name="no-project-ds",
            ls_project_id=None,
        )

        repo_mock = AsyncMock()
        repo_mock.get_dataset = AsyncMock(return_value=dataset_no_project)

        mock_cfg2 = MagicMock()
        mock_cfg2.db.auto_create = True

        with TestClient(app) as c:
            with patch.object(main_module.container, "config", return_value=mock_cfg2):
                with patch.object(main_module.container, "repository", return_value=repo_mock):
                    r = c.post(
                        f"/api/v1/datasets/{dataset_no_project.id}/samples",
                        json=_SAMPLE_PAYLOAD,
                    )

        assert r.status_code == 500
        assert "no Label Studio project" in r.json()["detail"]
    finally:
        _reset_container_overrides()


# ---------------------------------------------------------------------------
# test_create_sample_ls_task_creation_fails_returns_502
# ---------------------------------------------------------------------------


def test_create_sample_ls_task_creation_fails_returns_502() -> None:
    """When LS task creation fails, sample creation returns 502."""
    from app.domain.models import Dataset, Sample
    from unittest.mock import patch
    from uuid import uuid4

    import app.main as main_module

    dataset = Dataset(
        id=str(uuid4()),
        name="task-fail-ds",
        ls_project_id="10",
    )

    sample = Sample(
        id=str(uuid4()),
        dataset_id=dataset.id,
        image_uris=["memory://samples/test.jpg"],
        metadata={},
    )

    repo_mock = AsyncMock()
    repo_mock.get_dataset = AsyncMock(return_value=dataset)
    repo_mock.create_sample = AsyncMock(return_value=sample)

    mock_ls = AsyncMock()
    mock_ls.create_task = AsyncMock(side_effect=RuntimeError("LS connection refused"))

    with TestClient(app) as c:
        with patch.object(main_module.container, "config", return_value=MagicMock()):
            with patch.object(main_module.container, "repository", return_value=repo_mock):
                with patch.object(main_module.container, "label_studio_client", return_value=mock_ls):
                    r = c.post(
                        f"/api/v1/datasets/{dataset.id}/samples",
                        json=_SAMPLE_PAYLOAD,
                    )

    assert r.status_code == 502
    assert "Label Studio task creation failed" in r.json()["detail"]


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
