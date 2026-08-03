from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

from app import perspective_main


def test_current_rss_mb_reads_proc_status(tmp_path: Path) -> None:
    status = tmp_path / "status"
    status.write_text("Name:\tuvicorn\nVmRSS:\t2048 kB\n", encoding="utf-8")

    assert perspective_main._current_rss_mb(status) == 2


def test_configured_max_rss_mb_is_optional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PERSPECTIVE_WS_MAX_RSS_MB", raising=False)

    assert perspective_main._configured_max_rss_mb() is None


def test_configured_max_rss_mb_rejects_non_positive_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PERSPECTIVE_WS_MAX_RSS_MB", "0")

    with pytest.raises(ValueError, match="must be greater than zero"):
        perspective_main._configured_max_rss_mb()


def test_health_records_memory_usage_without_a_kill_line(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(perspective_main, "_configured_max_rss_mb", lambda: None)
    monkeypatch.setattr(perspective_main, "_current_rss_mb", lambda: 75.25)
    caplog.set_level(logging.INFO, logger=perspective_main.__name__)

    response = perspective_main.health()

    assert response == {"status": "ok"}
    assert (
        "Perspective memory usage endpoint=/health "
        "rss_mb=75.2 max_rss_mb=disabled"
    ) in caplog.messages


@pytest.mark.asyncio
async def test_readiness_rejects_memory_pressure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(perspective_main, "_configured_max_rss_mb", lambda: 100)
    monkeypatch.setattr(perspective_main, "_current_rss_mb", lambda: 101)
    caplog.set_level(logging.INFO, logger=perspective_main.__name__)
    request = cast(Request, SimpleNamespace())

    response = await perspective_main.readiness(request)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    assert (
        "Perspective memory usage endpoint=/ready "
        "rss_mb=101.0 max_rss_mb=100.0"
    ) in caplog.messages
