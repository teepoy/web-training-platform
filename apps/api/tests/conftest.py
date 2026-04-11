from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os

os.environ.setdefault("APP_CONFIG_PROFILE", "test")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///./finetune-test-{uuid4().hex}.db")


# ---------------------------------------------------------------------------
# Clean DB at the start of each test session
#
# The test profile uses SQLite. Without cleanup
# previous test data survives across runs, causing 409 Conflict errors
# when auth tests try to register the same email addresses.
# ---------------------------------------------------------------------------

import asyncio


def _reset_database() -> None:
    """Drop all tables and recreate them so every test session starts clean."""
    from app.core.config import load_config
    from app.db.session import create_engine as _create_engine
    from app.db.base import Base
    from app.db import models as _models  # noqa: F401 — ensure all models registered

    cfg = load_config()
    engine = _create_engine(str(cfg.db.url))

    async def _drop_and_create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_drop_and_create())

    # Reset the module-level session factory in deps.py so it doesn't
    # hold a stale connection to the old (dropped) tables.
    import app.api.deps as _deps
    _deps._session_factory = None


# Run once at import time (before any test or fixture executes).
_reset_database()


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


@pytest.fixture(autouse=True, scope="function")
def _mock_embedding_service(request):
    """Override the embedding service for tests by default.

    Feature extraction and related endpoints otherwise depend on an external
    gRPC embedding server, which can make the test suite block indefinitely
    when that service is unavailable.
    """
    if request.node.get_closest_marker("no_embedding_override"):
        yield
        return

    from app.main import container

    async def _embed_image(image_bytes: bytes, model_name: str = "openai/clip-vit-base-patch32") -> list[float]:
        size = max(1, len(image_bytes))
        base = min(1.0, size / 255.0)
        return [base, 0.5, 0.25, 0.125]

    async def _embed_batch(image_bytes_list: list[bytes], model_name: str = "openai/clip-vit-base-patch32") -> list[list[float]]:
        return [await _embed_image(image_bytes, model_name=model_name) for image_bytes in image_bytes_list]

    async def _classify_image(
        image_bytes: bytes,
        labels: list[str],
        model_name: str = "openai/clip-vit-base-patch32",
    ) -> tuple[str, float, dict[str, float]]:
        if not labels:
            return "", 0.0, {}
        score = 1.0 / len(labels)
        scores = {label: score for label in labels}
        return labels[0], score, scores

    async def _classify_batch(
        image_bytes_list: list[bytes],
        labels: list[str],
        model_name: str = "openai/clip-vit-base-patch32",
    ) -> list[tuple[str, float, dict[str, float]]]:
        return [await _classify_image(image_bytes, labels, model_name=model_name) for image_bytes in image_bytes_list]

    _mock_embedding = MagicMock()
    _mock_embedding.embed_image = AsyncMock(side_effect=_embed_image)
    _mock_embedding.embed_batch = AsyncMock(side_effect=_embed_batch)
    _mock_embedding.classify_image = AsyncMock(side_effect=_classify_image)
    _mock_embedding.classify_batch = AsyncMock(side_effect=_classify_batch)
    _mock_embedding.health = AsyncMock(return_value=True)

    container.embedding_service.override(providers.Object(_mock_embedding))
    yield
    container.embedding_service.reset_override()


# ---------------------------------------------------------------------------
# Preset registry helper
#
# After the preset refactor, presets are loaded from YAML files on disk
# (not from the database).  The registry is loaded during the FastAPI
# lifespan, but some test helpers need a known preset ID without going
# through the full app lifecycle.  This constant points to a preset that
# ships in the repo.
# ---------------------------------------------------------------------------

PRESET_ID = "resnet50-cls-v1"


@pytest.fixture(autouse=True, scope="function")
def _ensure_preset_registry():
    """Ensure the file-backed preset registry is loaded before each test.

    The registry is normally loaded in the FastAPI lifespan, which runs
    when ``TestClient(app)`` enters its context.  This fixture eagerly
    loads it so that tests that access the registry outside the TestClient
    context (rare) also work.
    """
    from app.main import container

    registry = container.preset_registry()
    if registry.count == 0:
        registry.load()
    yield


@pytest.fixture(autouse=True, scope="function")
def _dispose_db_resources():
    db_url = f"sqlite+aiosqlite:///./finetune-test-{uuid4().hex}.db"
    os.environ["DATABASE_URL"] = db_url

    from app.core.config import load_config
    from app.main import container
    import app.api.deps as _deps

    load_config.cache_clear()
    container.reset_singletons()
    _deps._session_factory = None

    yield

    async def _dispose() -> None:
        engine = container.db_engine()
        await engine.dispose()

    asyncio.run(_dispose())
    load_config.cache_clear()
    container.reset_singletons()
    _deps._session_factory = None
