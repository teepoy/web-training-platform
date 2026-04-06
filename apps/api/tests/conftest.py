from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os

os.environ.setdefault("APP_CONFIG_PROFILE", "local-smoke")


def _register_user(client, email: str, password: str, name: str) -> dict:
    """Call POST /api/v1/auth/register, return user dict"""
    resp = client.post("/api/v1/auth/register", json={"email": email, "password": password, "name": name})
    resp.raise_for_status()
    return resp.json()


def _login_user(client, email: str, password: str) -> str:
    """Call POST /api/v1/auth/login, return access_token string"""
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    resp.raise_for_status()
    return resp.json()["access_token"]


def _auth_headers(token: str) -> dict:
    """Return Authorization Bearer header dict"""
    return {"Authorization": f"Bearer {token}"}


def _org_headers(org_id: str, token: str) -> dict:
    """Return auth + org context headers"""
    return {"Authorization": f"Bearer {token}", "X-Organization-ID": org_id}


def _create_org(client, name: str, admin_token: str) -> dict:
    """Call POST /api/v1/organizations, return org dict. Stub — endpoint added in T12."""
    resp = client.post("/api/v1/organizations", json={"name": name}, headers=_auth_headers(admin_token))
    resp.raise_for_status()
    return resp.json()


def _add_member(client, org_id: str, user_id: str, role: str, admin_token: str) -> dict:
    """Add user to org. Stub — endpoint added in T12."""
    resp = client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"user_id": user_id, "role": role},
        headers=_auth_headers(admin_token),
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Auth dependency overrides for existing tests
#
# Existing tests (test_api_flows, test_annotation_crud, etc.) do NOT send
# auth headers.  After T11, all resource routes require auth + org context.
# We override the FastAPI dependencies globally for all non-auth tests so
# existing tests keep passing without modification.
#
# test_auth_routes.py opts OUT of these overrides by clearing them with the
# `no_auth_override` marker — see that file for details.
# ---------------------------------------------------------------------------

import pytest
from fastapi.testclient import TestClient

DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000002"


@pytest.fixture(autouse=True, scope="function")
def _mock_auth_deps(request):
    """Override get_current_user and get_current_org for all tests by default.

    Tests that need real auth enforcement should either:
    - Use the ``no_auth_override`` marker, OR
    - Be in test_auth.py or test_auth_routes.py (automatically skipped)
    """
    # Allow specific tests to opt out of the override
    if request.node.get_closest_marker("no_auth_override"):
        yield
        return

    # Skip override for auth-specific test modules that test real auth behavior
    module_name = getattr(request.module, "__name__", "")
    if module_name in ("test_auth", "test_auth_routes"):
        yield
        return

    from app.main import app
    from app.api.deps import get_current_user, get_current_org
    from app.domain.models import User, Organization
    import datetime

    _mock_user = User(
        id=DEFAULT_USER_ID,
        email="test@test.com",
        name="Test User",
        is_superadmin=True,
        is_active=True,
        created_at=datetime.datetime(2024, 1, 1),
    )
    _mock_org = Organization(
        id=DEFAULT_ORG_ID,
        name="Default",
        slug="default",
        created_at=datetime.datetime(2024, 1, 1),
    )

    app.dependency_overrides[get_current_user] = lambda: _mock_user
    app.dependency_overrides[get_current_org] = lambda: _mock_org
    yield
    # Clean up overrides after each test
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_org, None)


# ---------------------------------------------------------------------------
# Label Studio client override for non-LS tests
#
# After the LS-always-on migration, create_dataset always calls LS to create
# a project.  Non-LS tests don't mock LS themselves, so we provide a global
# mock that succeeds silently.  Tests in test_ls_*.py manage their own
# overrides — they call container.label_studio_client.override() directly
# and reset it in their finally blocks.
# ---------------------------------------------------------------------------

from unittest.mock import AsyncMock, MagicMock
from dependency_injector import providers


@pytest.fixture(autouse=True, scope="function")
def _mock_ls_client(request):
    """Override the LS client for all tests by default.

    Tests that manage their own LS client overrides (test_ls_* modules) opt
    out via the ``no_ls_override`` marker or by being in a module whose name
    starts with ``test_ls_``.
    """
    if request.node.get_closest_marker("no_ls_override"):
        yield
        return

    module_name = getattr(request.module, "__name__", "").rsplit(".", 1)[-1]
    if module_name.startswith("test_ls_") or module_name == "test_label_studio_client":
        yield
        return

    from app.main import container

    _mock_ls = MagicMock()
    _mock_ls.create_project = AsyncMock(return_value={"id": 1, "title": "mock-project"})
    _mock_ls.update_project = AsyncMock(return_value={"id": 1, "title": "mock-project"})
    _mock_ls.create_task = AsyncMock(return_value={"id": 1})
    _mock_ls.create_annotation = AsyncMock(return_value={"id": 0, "task": 0, "result": []})
    _mock_ls.list_tasks = AsyncMock(return_value=([], 0))
    _mock_ls.list_annotations = AsyncMock(return_value=[])
    _mock_ls.export_project = AsyncMock(return_value=[])

    container.label_studio_client.override(providers.Object(_mock_ls))
    yield
    container.label_studio_client.reset_override()
