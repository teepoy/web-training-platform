from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.config import load_config
from app.modules.sc.domain.upstream_reader import ScUpstreamReader
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.perspective_composition import (
    build_perspective_app_context,
    close_perspective_app_context,
)
from app.shared.db.session import AppDatabaseSessionFactory


@pytest.mark.asyncio
async def test_perspective_composition_only_builds_dataset_storage_on_demand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SC_UPSTREAM_ADDR", "sc-upstream:9091")
    monkeypatch.setenv(
        "SC_UPSTREAM_FLIGHT_ADDR",
        "grpc://sc-upstream:9093",
    )
    storage_factory = object()
    build_storage = MagicMock(return_value=storage_factory)
    monkeypatch.setattr(
        "app.perspective_composition._build_dataset_storage_factory",
        build_storage,
    )
    ctx = build_perspective_app_context(
        load_config(skip_runtime_validation=True),
    )

    try:
        assert (
            ctx.injector.get(AppDatabaseSessionFactory)
            is ctx.shared.session_factory
        )
        assert ctx.injector.get(ScUpstreamReader) is ctx.upstream_reader
        build_storage.assert_not_called()

        assert ctx.injector.get(DatasetStorageFactoryPort) is storage_factory
        build_storage.assert_called_once()
    finally:
        await close_perspective_app_context(ctx)


def test_perspective_composition_requires_explicit_upstream_addresses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SC_UPSTREAM_ADDR", raising=False)
    monkeypatch.delenv("SC_UPSTREAM_FLIGHT_ADDR", raising=False)

    with pytest.raises(
        RuntimeError,
        match="SC_UPSTREAM_ADDR",
    ):
        build_perspective_app_context(
            load_config(skip_runtime_validation=True),
        )
