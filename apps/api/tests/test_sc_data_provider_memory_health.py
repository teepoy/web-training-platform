from __future__ import annotations

import logging
import os
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

from app import sc_data_provider_main
from app.core.config import load_config


def _request() -> Request:
    config = load_config(skip_runtime_validation=True).sc.data_provider
    return cast(
        Request,
        SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    sc_data_provider=SimpleNamespace(
                        config=config,
                        executor=SimpleNamespace(temp_directory_size_bytes=lambda: 0),
                    ),
                )
            )
        ),
    )


def test_current_rss_mb_reads_proc_status(tmp_path: Path) -> None:
    status = tmp_path / "status"
    status.write_text("Name:\tuvicorn\nVmRSS:\t2048 kB\n", encoding="utf-8")

    assert sc_data_provider_main._current_rss_mb(status) == 2


def test_health_records_memory_usage_on_every_call(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(sc_data_provider_main, "_current_rss_mb", lambda: 75.25)
    caplog.set_level(logging.INFO, logger=sc_data_provider_main.__name__)

    first = sc_data_provider_main.health(_request())
    second = sc_data_provider_main.health(_request())

    assert first == second == {
        "status": "ok",
        "rss_mb": 75.25,
        "duckdb_temp_bytes": 0,
        "worker_pid": os.getpid(),
    }
    assert caplog.messages.count(
        "SC data-provider memory usage endpoint=/health rss_mb=75.2 max_rss_mb=1536"
    ) == 2


@pytest.mark.asyncio
async def test_readiness_rejects_memory_pressure_before_dependency_checks(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(sc_data_provider_main, "_current_rss_mb", lambda: 1536.5)
    caplog.set_level(logging.INFO, logger=sc_data_provider_main.__name__)

    response = await sc_data_provider_main.readiness(_request())

    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    assert (
        "SC data-provider memory usage endpoint=/ready "
        "rss_mb=1536.5 max_rss_mb=1536"
    ) in caplog.messages


def test_config_rejects_unsupported_worker_thread_count() -> None:
    config = load_config(skip_runtime_validation=True).sc.data_provider.model_copy(
        update={"duckdb_threads": 2}
    )

    with pytest.raises(RuntimeError, match="must be 1 per worker"):
        sc_data_provider_main._validate_data_provider_config(config)


def test_config_rejects_declared_workers_that_exceed_container_capacity() -> None:
    config = load_config(skip_runtime_validation=True).sc.data_provider.model_copy(
        update={
            "worker_count": 4,
            "container_memory_limit_mb": 5_000,
            "python_overhead_mb": 256,
            "service_headroom_mb": 512,
        }
    )

    with pytest.raises(RuntimeError, match="capacity exceeds its container limit"):
        sc_data_provider_main._validate_data_provider_config(config)
