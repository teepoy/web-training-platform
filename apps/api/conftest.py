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
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
os.environ.setdefault(
    "DATABASE_URL", f"sqlite+aiosqlite:///./finetune-test-{uuid4().hex}.db"
)
os.environ.setdefault("SC_UPSTREAM_ADDR", "localhost:9091")
os.environ.setdefault("SC_UPSTREAM_FLIGHT_ADDR", "grpc://localhost:9093")
os.environ.setdefault("IMAGE_PARSER_GRPC_ADDR", "localhost:9092")
os.environ.setdefault("SC_DATA_PROVIDER_CACHE_DIR", "/tmp/sc-data-provider-tests")
os.environ.setdefault("SC_DATA_PROVIDER_CACHE_NAMESPACE", "sc-data-provider-tests")

from app.shared.infrastructure.storage.factory import (  # noqa: E402
    register_artifact_storage_factory,
)
from tests.support.artifact_storage import InMemoryArtifactStorage  # noqa: E402
from app.modules.training.adapter.engines.registry import (  # noqa: E402
    register_training_engine_factory,
)
from tests.support.local_training_engine import LocalProcessEngine  # noqa: E402

register_artifact_storage_factory("memory", lambda _cfg: InMemoryArtifactStorage())
register_training_engine_factory("local", lambda storage: LocalProcessEngine(storage))

_OPEN_CONTAINERS = []

_INTEGRATION_TEST_PATH_PREFIXES = (
    "tests/test_api_flows.py",
    "tests/test_pubsub_events.py",
    "app/modules/agent/tests/test_agent.py",
    "app/modules/agent/tests/test_global_agent.py",
    "app/modules/datasets/tests/",
    "app/modules/jobs/schedules/tests/",
    "app/modules/jobs/task_tracker/tests/",
    "app/modules/prediction/tests/test_prediction_review.py",
    "app/modules/prediction/tests/test_prediction_routes.py",
    "app/modules/sc/tests/test_sc_import_endpoint.py",
    "app/modules/sc/tests/test_sc_import_service.py",
    "app/modules/sc/tests/test_sc_import_sparse_bytes.py",
    "app/modules/sc/tests/test_sc_inspections.py",
    "app/modules/sc/tests/test_sc_plot_points.py",
    "app/modules/training/tests/test_training_runner.py",
)

_DEV_SERVER_TEST_PATH_PREFIXES = ("tests/test_data_integrity.py",)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-dev-server",
        action="store_true",
        default=False,
        help="Collect and run tests that require a running local dev API/server.",
    )


def pytest_ignore_collect(
    collection_path: Path,
    config: pytest.Config,
) -> bool:
    try:
        rel_path = collection_path.relative_to(ROOT).as_posix()
    except ValueError:
        return False
    if rel_path.startswith(_DEV_SERVER_TEST_PATH_PREFIXES):
        return not bool(config.getoption("--run-dev-server"))
    return False


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    integration_marker = pytest.mark.integration(
        reason="API/module integration coverage"
    )
    dev_server_marker = pytest.mark.dev_server(
        reason="Requires a running local dev API/server; run explicitly with --run-dev-server"
    )
    skip_dev_server_marker = pytest.mark.skip(
        reason="Requires a running local dev API/server; pass --run-dev-server to run"
    )
    run_dev_server = bool(config.getoption("--run-dev-server"))
    for item in items:
        rel_path = item.path.relative_to(ROOT).as_posix()
        if rel_path.startswith(_INTEGRATION_TEST_PATH_PREFIXES):
            item.add_marker(integration_marker)
        if rel_path.startswith(_DEV_SERVER_TEST_PATH_PREFIXES):
            item.add_marker(dev_server_marker)
            if not run_dev_server:
                item.add_marker(skip_dev_server_marker)


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

    app.dependency_overrides[agent_get_ls_client] = lambda: _mock_ls
    app.dependency_overrides[datasets_get_ls_client] = lambda: _mock_ls
    yield
    app.dependency_overrides.pop(agent_get_ls_client, None)
    app.dependency_overrides.pop(datasets_get_ls_client, None)


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
