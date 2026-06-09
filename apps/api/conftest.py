from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[0]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("APP_CONFIG_PROFILE", "test")
os.environ.setdefault(
    "DATABASE_URL", f"sqlite+aiosqlite:///./finetune-test-{uuid4().hex}.db"
)

_OPEN_CONTAINERS = []


@pytest.fixture(autouse=True, scope="function")
def _ensure_registrations_loaded():
    import app.registrations as _  # noqa: F401 — triggers decorator-based registrations

    yield


@pytest.fixture(autouse=True, scope="function")
def _dispose_db_resources():
    db_url = f"sqlite+aiosqlite:///./finetune-test-{uuid4().hex}.db"
    os.environ["DATABASE_URL"] = db_url

    from app.core.config import load_config

    load_config.cache_clear()

    yield

    async def _dispose() -> None:
        while _OPEN_CONTAINERS:
            container = _OPEN_CONTAINERS.pop()
            close = getattr(container, "close", None)
            if close is not None:
                await close()

    asyncio.run(_dispose())

    _db_path = db_url.removeprefix("sqlite+aiosqlite:///")
    for _suffix in ("", "-wal", "-shm"):
        _p = Path(_db_path + _suffix)
        try:
            _p.unlink(missing_ok=True)
        except OSError:
            pass

    load_config.cache_clear()


# Auth fixture available globally (root conftest) so tests under
# app/modules/*/tests/ also get auth mocks without relying on
# pytest_plugins = ["tests.conftest"] (which causes double registration
# when tests are run from the tests/ directory).
DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000002"

from app.shared.api.schemas import Organization as _Organization, User as _User  # noqa: E402


@pytest.fixture(autouse=True, scope="function")
def _mock_auth_deps(request, monkeypatch):
    if request.node.get_closest_marker("no_auth_override"):
        yield
        return

    module_name = getattr(request.module, "__name__", "")
    if module_name in ("test_auth", "test_auth_routes"):
        yield
        return

    from datetime import datetime as _datetime

    from app.main import app
    from app.modules.auth.port.http.deps import (
        get_current_org,
        get_current_user,
    )

    _default_user = _User(
        id=DEFAULT_USER_ID,
        email="test@test.com",
        name="Test User",
        is_superadmin=True,
        created_at=_datetime(2024, 1, 1),
    )
    _default_org = _Organization(
        id=DEFAULT_ORG_ID,
        name="Default",
        slug="default",
        created_at=_datetime(2024, 1, 1),
    )
    app.dependency_overrides[get_current_user] = lambda: _default_user
    app.dependency_overrides[get_current_org] = lambda: _default_org
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_org, None)


@pytest.fixture(autouse=True, scope="function")
def _mock_ls_client(request):
    from unittest.mock import AsyncMock, MagicMock

    if request.node.get_closest_marker("no_ls_override"):
        yield
        return

    module_name = getattr(request.module, "__name__", "").rsplit(".", 1)[-1]
    if module_name.startswith("test_ls_"):
        yield
        return

    _mock_ls = MagicMock()
    _mock_ls.create_project = AsyncMock(return_value={"id": 1, "title": "mock-project"})
    _mock_ls.update_project = AsyncMock(return_value={"id": 1, "title": "mock-project"})
    _mock_ls.delete_project = AsyncMock(return_value=None)
    _mock_ls.create_task = AsyncMock(return_value={"id": 1})
    _mock_ls.import_tasks = AsyncMock(
        side_effect=lambda project_id, tasks, return_task_ids=True: {
            "task_ids": list(range(1, len(tasks) + 1)),
            "task_count": len(tasks),
        }
    )
    _mock_ls.create_annotation = AsyncMock(
        return_value={"id": 0, "task": 0, "result": []}
    )
    _mock_ls.list_tasks = AsyncMock(return_value=([], 0))
    _mock_ls.list_annotations = AsyncMock(return_value=[])
    _mock_ls.export_project = AsyncMock(return_value=[])

    from app.main import app
    from app.modules.datasets.port.http.deps import (
        get_label_studio_client as datasets_get_ls_client,
    )
    from app.modules.agent.port.http.deps import (
        get_label_studio_client as agent_get_ls_client,
    )
    from app.modules.preview.port.http.deps import (
        get_label_studio_client as preview_get_ls_client,
    )

    app.dependency_overrides[agent_get_ls_client] = lambda: _mock_ls
    app.dependency_overrides[datasets_get_ls_client] = lambda: _mock_ls
    app.dependency_overrides[preview_get_ls_client] = lambda: _mock_ls
    yield
    app.dependency_overrides.pop(agent_get_ls_client, None)
    app.dependency_overrides.pop(datasets_get_ls_client, None)
    app.dependency_overrides.pop(preview_get_ls_client, None)


@pytest.fixture(autouse=True, scope="function")
def _assert_clean_overrides():
    """Ensures tests using app.dependency_overrides[get_xxx] = fake properly clean up."""
    from app.main import app

    initial = dict(app.dependency_overrides)
    yield
    leaked_keys = set(app.dependency_overrides) - set(initial)
    for key in list(app.dependency_overrides.keys()):
        if key not in initial:
            del app.dependency_overrides[key]
    assert not leaked_keys, f"Test leaked dependency_overrides: {leaked_keys}"
    assert dict(app.dependency_overrides) == initial, (
        f"Test leaked dependency_overrides: {set(app.dependency_overrides) - set(initial)}"
    )
