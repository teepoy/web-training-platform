from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core import platform_setup
from app.core.config import AppConfig
from app.shared.context import SharedInfra
from app.shared.infrastructure.prefect.client import PrefectClient


@pytest.mark.asyncio
async def test_prepare_platform_rejects_a_concurrent_runner(monkeypatch) -> None:
    connection = AsyncMock()
    connection.scalar.return_value = False

    class _ConnectionContext:
        async def __aenter__(self):
            return connection

        async def __aexit__(self, *_args):
            return None

    engine = SimpleNamespace(
        connect=lambda: _ConnectionContext(),
        dispose=AsyncMock(),
    )
    prefect = SimpleNamespace(close=AsyncMock())
    shared = SimpleNamespace(db_engine=engine, prefect_client=prefect)
    monkeypatch.setattr(platform_setup, "build_shared_infra", lambda _config: shared)

    config = cast(AppConfig, SimpleNamespace(app=SimpleNamespace(env="dev")))
    with pytest.raises(RuntimeError, match="already running"):
        await platform_setup.prepare_platform(config)

    connection.commit.assert_awaited_once()
    prefect.close.assert_awaited_once()
    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_prefect_create_conflicts_are_reread_and_converged() -> None:
    client = PrefectClient("http://prefect.test/api")
    client._request = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            [],
            [],
            None,
            [{"id": "flow-id"}],
            None,
            [{"id": "deployment-id"}],
            None,
            {
                "id": "deployment-id",
                "flow_id": "flow-id",
                "work_pool_name": "default-cpu",
                "entrypoint": "module:flow",
                "path": "",
            },
        ]
    )
    try:
        deployment = await client.ensure_deployment(
            deployment_name="example",
            flow_name="example-flow",
            work_pool_name="default-cpu",
            entrypoint="module:flow",
            path="",
        )
    finally:
        await client.close()

    assert deployment["id"] == "deployment-id"
    patch_call = client._request.await_args_list[-2]  # type: ignore[attr-defined]
    assert patch_call.args == ("PATCH", "/deployments/deployment-id")
    assert patch_call.kwargs["json"] == {
        "work_pool_name": "default-cpu",
        "entrypoint": "module:flow",
        "path": "",
    }


@pytest.mark.asyncio
async def test_dependency_validation_is_read_only_and_complete(monkeypatch) -> None:
    async_checks = {
        "database": AsyncMock(),
        "prefect": AsyncMock(),
        "label_studio": AsyncMock(),
        "redis": AsyncMock(),
    }
    minio_check = MagicMock()
    monkeypatch.setattr(
        platform_setup, "validate_database_revision", async_checks["database"]
    )
    monkeypatch.setattr(platform_setup, "_validate_minio", minio_check)
    monkeypatch.setattr(platform_setup, "validate_prefect", async_checks["prefect"])
    monkeypatch.setattr(
        platform_setup, "validate_label_studio", async_checks["label_studio"]
    )
    monkeypatch.setattr(platform_setup, "validate_redis", async_checks["redis"])

    config = cast(AppConfig, SimpleNamespace())
    shared = cast(SharedInfra, SimpleNamespace())
    await platform_setup.validate_platform_dependencies(config, shared)

    for check in async_checks.values():
        check.assert_awaited_once()
    minio_check.assert_called_once_with(config, shared)
