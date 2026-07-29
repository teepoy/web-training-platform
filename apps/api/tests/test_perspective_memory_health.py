from __future__ import annotations

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


@pytest.mark.asyncio
async def test_readiness_rejects_memory_pressure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(perspective_main, "_configured_max_rss_mb", lambda: 100)
    monkeypatch.setattr(perspective_main, "_current_rss_mb", lambda: 101)
    request = cast(Request, SimpleNamespace())

    response = await perspective_main.readiness(request)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
