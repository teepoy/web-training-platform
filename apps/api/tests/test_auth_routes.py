"""Tests for auth enforcement on resource routes.

These tests verify that resource routes return 401 when no auth is provided
and 200 when authenticated with proper org context.

Uses the ``no_auth_override`` marker to bypass the global auth mock in conftest.py,
so the real auth enforcement is tested.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.db.models import UserORM, OrgMembershipORM, OrganizationORM


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient, email: str, password: str, name: str):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": name},
    )


def _login(client: TestClient, email: str, password: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    resp.raise_for_status()
    return resp.json()["access_token"]


async def _promote_superadmin(email: str) -> None:
    from app.api.deps import _get_session_factory
    sf = _get_session_factory()
    async with sf() as session:
        result = await session.execute(select(UserORM).where(UserORM.email == email))
        user = result.scalar_one_or_none()
        if user is not None:
            user.is_superadmin = True
            await session.commit()


async def _get_user_id(email: str) -> str:
    from app.api.deps import _get_session_factory
    sf = _get_session_factory()
    async with sf() as session:
        result = await session.execute(select(UserORM).where(UserORM.email == email))
        user = result.scalar_one_or_none()
        return user.id if user else ""


def _make_superadmin_with_org(client: TestClient, email: str, password: str, name: str) -> tuple[str, str]:
    """Register + promote to superadmin, create org, return (token, org_id)."""
    _register(client, email, password, name).raise_for_status()
    asyncio.get_event_loop().run_until_complete(_promote_superadmin(email))
    token = _login(client, email, password)
    # Create an org
    org_resp = client.post(
        "/api/v1/organizations",
        json={"name": f"Test Org {email}", "slug": f"test-org-{email.replace('@', '-').replace('.', '-')}"},
        headers={"Authorization": f"Bearer {token}"},
    )
    org_resp.raise_for_status()
    org_id = org_resp.json()["id"]
    return token, org_id


# ---------------------------------------------------------------------------
# Auth enforcement tests (opt out of global auth mock)
# ---------------------------------------------------------------------------


@pytest.mark.no_auth_override
def test_unauthenticated_dataset_list_returns_401() -> None:
    """GET /api/v1/datasets without auth token must return 401."""
    with TestClient(app) as c:
        resp = c.get("/api/v1/datasets")
        assert resp.status_code == 401


@pytest.mark.no_auth_override
def test_authenticated_dataset_list_returns_200() -> None:
    """GET /api/v1/datasets with valid auth + org context must return 200."""
    with TestClient(app) as c:
        token, org_id = _make_superadmin_with_org(
            c,
            "auth_ds_list@test.com",
            "pass123",
            "Auth DS User",
        )
        resp = c.get(
            "/api/v1/datasets",
            headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


@pytest.mark.no_auth_override
def test_unauthenticated_jobs_returns_401() -> None:
    """GET /api/v1/training-jobs without auth token must return 401."""
    with TestClient(app) as c:
        resp = c.get("/api/v1/training-jobs")
        assert resp.status_code == 401


@pytest.mark.no_auth_override
def test_health_endpoint_no_auth_needed() -> None:
    """GET /health must return 200 without any auth token."""
    with TestClient(app) as c:
        resp = c.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
