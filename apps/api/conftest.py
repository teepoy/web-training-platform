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

    load_config.cache_clear()
    container.reset_singletons()

    yield

    async def _dispose() -> None:
        engine = container.db_engine()
        await engine.dispose()

    asyncio.run(_dispose())

    _db_path = db_url.removeprefix("sqlite+aiosqlite:///")
    for _suffix in ("", "-wal", "-shm"):
        _p = Path(_db_path + _suffix)
        try:
            _p.unlink(missing_ok=True)
        except OSError:
            pass

    load_config.cache_clear()
    container.reset_singletons()
