"""Tests for LS-hosted image resolution endpoint."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.modules.models.port.http.deps import get_artifact_storage, get_config


def _make_config(url: str = "http://label-studio:8080") -> MagicMock:
    cfg = MagicMock()
    cfg.label_studio.url = url
    cfg.label_studio.api_key = "fake-key"
    return cfg


def _make_storage() -> AsyncMock:
    storage = AsyncMock()
    storage.get_bytes = AsyncMock(return_value=b"memory-image-bytes")
    return storage


def test_http_uri_allowed_when_ls_url_matches() -> None:
    mock_config = _make_config("http://label-studio:8080")
    mock_response = MagicMock()
    mock_response.content = b"\x89PNG\r\n\x1a\nimage-bytes"
    mock_response.headers = {"content-type": "image/png"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with TestClient(app) as c:
        app.dependency_overrides[get_config] = lambda: mock_config
        with patch("httpx.AsyncClient", return_value=mock_client):
            r = c.get(
                "/api/v1/images/resolve",
                params={"uri": "http://label-studio:8080/data/upload/image.jpg"},
            )
        app.dependency_overrides.pop(get_config, None)

    assert r.status_code == 200
    assert r.content == mock_response.content
    assert r.headers["content-type"] == "image/png"


def test_http_uri_rejected_when_ls_url_empty() -> None:
    mock_config = _make_config("")

    with TestClient(app) as c:
        app.dependency_overrides[get_config] = lambda: mock_config
        r = c.get(
            "/api/v1/images/resolve",
            params={"uri": "http://label-studio:8080/data/upload/image.jpg"},
        )
        app.dependency_overrides.pop(get_config, None)

    assert r.status_code == 400
    assert r.json()["detail"] == "http/https URIs are not allowed"


def test_http_uri_rejected_from_wrong_origin() -> None:
    mock_config = _make_config("http://label-studio:8080")

    with TestClient(app) as c:
        app.dependency_overrides[get_config] = lambda: mock_config
        r = c.get(
            "/api/v1/images/resolve",
            params={"uri": "http://evil.com/image.jpg"},
        )
        app.dependency_overrides.pop(get_config, None)

    assert r.status_code == 400
    assert r.json()["detail"] == "http/https URIs are not allowed"


def test_data_uri_still_works() -> None:
    data_uri = "data:image/png;base64,iVBORw0KGgo="

    with TestClient(app) as c:
        app.dependency_overrides[get_config] = lambda: _make_config("http://label-studio:8080")
        r = c.get("/api/v1/images/resolve", params={"uri": data_uri})
        app.dependency_overrides.pop(get_config, None)

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/png")


def test_storage_uri_still_works() -> None:
    storage = _make_storage()

    with TestClient(app) as c:
        app.dependency_overrides[get_artifact_storage] = lambda: storage
        r = c.get(
            "/api/v1/images/resolve",
            params={"uri": "memory://samples/1/image.png"},
        )
        app.dependency_overrides.pop(get_artifact_storage, None)

    assert r.status_code == 200
    assert r.content == b"memory-image-bytes"
    assert r.headers["content-type"] == "image/png"
