from __future__ import annotations

"""Tests for POST /sc/import endpoint.

TDD: RED phase — these tests MUST fail before the route is implemented.
"""

import datetime  # noqa: E402
import os  # noqa: E402
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

import pytest  # noqa: E402

# Force test profile so auth.enabled=true (dev profile has auth disabled).
# Must run BEFORE any app-level imports.
os.environ["APP_CONFIG_PROFILE"] = "test"

from app.core.config import load_config  # noqa: E402

load_config.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.modules.auth.port.http.deps import get_current_org, get_current_user  # noqa: E402
from app.modules.sc.domain.entities.sc_import import ScImportStatus  # noqa: E402
from app.modules.sc.port.http.deps import get_sc_import_service  # noqa: E402
from app.shared.api.schemas import Organization, User  # noqa: E402

_MOCK_USER = User(
    id="00000000-0000-0000-0000-000000000002",
    email="test@test.com",
    name="Test User",
    is_superadmin=True,
    is_active=True,
    created_at=datetime.datetime(2024, 1, 1),
)
_MOCK_ORG = Organization(
    id="00000000-0000-0000-0000-000000000001",
    name="Default",
    slug="default",
    created_at=datetime.datetime(2024, 1, 1),
)

_VALID_BODY: dict[str, object] = {
    "source_inspection_time": "2024-01-15T08:30:00",
    "source_wafer_key": 1,
    "dataset_name": "test-sc-dataset",
    "storage_mode": "file_shard_sparse",
    "filters": None,
    "label_space": ["defect", "clean"],
}


def _mock_auth() -> None:
    app.dependency_overrides[get_current_user] = lambda: _MOCK_USER
    app.dependency_overrides[get_current_org] = lambda: _MOCK_ORG


def _unmock_auth() -> None:
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_org, None)


def _set_service_mock(mock_service: MagicMock) -> None:
    app.dependency_overrides[get_sc_import_service] = lambda: mock_service


def _unset_service_mock() -> None:
    app.dependency_overrides.pop(get_sc_import_service, None)


def test_post_import_success_returns_202() -> None:
    mock_service = MagicMock()
    mock_status = ScImportStatus(
        status="running",
        flow_run_id="flow-run-abc123",
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=1,
        dataset_name="test-sc-dataset",
        storage_mode="file_shard_sparse",
    )
    mock_service.submit_import = AsyncMock(
        return_value=(mock_status, "flow-run-abc123")
    )

    _mock_auth()
    _set_service_mock(mock_service)
    try:
        with TestClient(app) as client:
            resp = client.post("/api/v1/sc/import", json=_VALID_BODY)
            assert resp.status_code == 202, resp.text
            body = resp.json()
            assert body["flow_run_id"] == "flow-run-abc123"
            assert body["status"] == "running"
    finally:
        _unmock_auth()
        _unset_service_mock()


@pytest.mark.no_auth_override
def test_post_import_missing_auth_returns_401() -> None:
    with TestClient(app) as client:
        resp = client.post("/api/v1/sc/import", json=_VALID_BODY)
        assert resp.status_code == 401, resp.text


def test_post_import_invalid_body_returns_422() -> None:
    _mock_auth()
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/sc/import",
                json={"source_inspection_time": "2024-01-15T08:30:00"},
            )
            assert resp.status_code == 422, resp.text
    finally:
        _unmock_auth()


def test_post_import_prefect_unavailable_returns_200_fallback() -> None:
    mock_service = MagicMock()
    mock_status = ScImportStatus(
        status="failed",
        error="Prefect API error: Connection refused",
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=1,
        dataset_name="test-sc-dataset",
        storage_mode="file_shard_sparse",
    )
    mock_service.submit_import = AsyncMock(return_value=(mock_status, None))

    _mock_auth()
    _set_service_mock(mock_service)
    try:
        with TestClient(app) as client:
            resp = client.post("/api/v1/sc/import", json=_VALID_BODY)
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["status"] == "failed"
            assert body["flow_run_id"] is None
            assert "Prefect API error" in (body.get("error") or "")
    finally:
        _unmock_auth()
        _unset_service_mock()
