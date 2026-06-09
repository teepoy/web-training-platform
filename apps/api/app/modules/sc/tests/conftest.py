from __future__ import annotations

import tempfile
from collections.abc import Generator

import pytest

from app.modules.sc.adapter import ScDatasetStore
from app.modules.sc.adapter._wafer_mock.sqlite_upstream import SqliteScUpstream
from app.modules.sc.tests.db_fixture import create_mock_sc_db, teardown_mock_sc_db
from app.modules.sc.adapter._wafer_mock.cache import PatchImageCache


@pytest.fixture
def mock_sc_db_path() -> Generator[str, None, None]:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    create_mock_sc_db(db_path)
    yield db_path
    teardown_mock_sc_db(db_path)


@pytest.fixture
def mock_sc_db(mock_sc_db_path: str) -> Generator[str, None, None]:
    yield mock_sc_db_path


@pytest.fixture
def mock_wafer_db_reader(mock_sc_db_path: str) -> SqliteScUpstream:
    return SqliteScUpstream(db_url=f"sqlite:///{mock_sc_db_path}")


@pytest.fixture
def mock_patch_image_cache() -> Generator[PatchImageCache, None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = PatchImageCache(
            cache_dir=tmpdir,
            ttl_seconds=60,
            max_size_bytes=10 * 1024 * 1024,
        )
        yield cache
        cache.clear()


@pytest.fixture
def sc_store() -> ScDatasetStore:
    return ScDatasetStore()


@pytest.fixture
def mock_prefect_client():

    class MockPrefectClient:
        async def resolve_deployment_id(self, name: str) -> str:
            return "test-deployment-id"

        async def create_flow_run_from_deployment(
            self, deployment_id: str, parameters: dict
        ) -> dict:
            return {"id": "test-run-id-123"}

        async def get_flow_run(self, run_id: str) -> dict:
            return {"state_type": "COMPLETED", "state_message": ""}

    return MockPrefectClient()


@pytest.fixture
def mock_ls_client():

    class MockLSClient:
        async def create_project(self, name: str, label_config: str) -> dict:
            return {"id": 99}

    return MockLSClient()
