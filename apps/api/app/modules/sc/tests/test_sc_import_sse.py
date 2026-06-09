from __future__ import annotations

"""Tests for GET /sc/import/{flow_run_id}/stream SSE endpoint.

These tests follow TDD: they must FAIL before the route is implemented (RED),
then PASS when the handler is added (GREEN).
"""

import asyncio

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.main import app
from app.modules.sc.port.http.deps import get_prefect_client


@pytest.fixture(autouse=True)
def _fast_polling():
    """Reduce the 3s SSE poll sleep to 0 while keeping short sleeps intact."""
    _original_sleep = asyncio.sleep

    async def _fast_sleep(delay: float, result=None):
        if delay >= 2.0:
            return await _original_sleep(0, result=result)
        return await _original_sleep(delay, result=result)

    asyncio.sleep = _fast_sleep
    yield
    asyncio.sleep = _original_sleep


class _MockPrefectClient:
    """Mock Prefect client that returns flow runs in sequence.

    Returns flow-run dicts with Prefect v3 top-level ``state_type`` /
    ``state_message`` keys (as expected by ``_prefect_state_type`` and
    ``_prefect_state_message`` in the SSE router).
    """

    def __init__(self, *flow_runs):
        self._flow_runs = list(flow_runs)
        self._call_count = 0

    async def get_flow_run(self, flow_run_id: str):
        if self._call_count < len(self._flow_runs):
            flow_run = self._flow_runs[self._call_count]
            self._call_count += 1
            if isinstance(flow_run, Exception):
                raise flow_run
            return flow_run
        raise HTTPException(status_code=404, detail="flow run not found")


@pytest.fixture
def _inject_mock_prefect():
    """Fixture that injects a mock Prefect client via dependency override.

    Returns a factory function: client = _inject_mock_prefect(flow_runs...).
    Cleans up the override automatically.
    """
    _mock = None
    _key = get_prefect_client

    def _install(*flow_runs):
        nonlocal _mock
        _mock = _MockPrefectClient(*flow_runs)
        app.dependency_overrides[_key] = lambda: _mock
        return _mock

    yield _install
    if _key in app.dependency_overrides:
        del app.dependency_overrides[_key]


def _consume_sse(client: TestClient, url: str) -> str:
    """Perform a GET that consumes the entire SSE stream into a string."""
    resp = client.get(url)
    return resp.text


def test_sse_stream_returns_text_event_stream(_inject_mock_prefect) -> None:
    _inject_mock_prefect(HTTPException(status_code=404, detail="flow run not found"))

    with TestClient(app) as client:
        resp = client.get("/api/v1/sc/import/test-id/stream")
        assert resp.status_code == 200
        content_type = resp.headers.get("content-type", "")
        assert "text/event-stream" in content_type


def test_sse_emits_error_when_not_found(_inject_mock_prefect) -> None:
    _inject_mock_prefect(HTTPException(status_code=404, detail="flow run not found"))

    with TestClient(app) as client:
        body = _consume_sse(client, "/api/v1/sc/import/nonexistent-id/stream")
        assert "event: error" in body
        assert "import flow run not found" in body.lower()


def test_sse_emits_done_when_completed(_inject_mock_prefect) -> None:
    _inject_mock_prefect({"state_type": "COMPLETED", "state_message": "done"})

    with TestClient(app) as client:
        body = _consume_sse(client, "/api/v1/sc/import/test-id/stream")
        assert "event: done" in body


def test_sse_emits_error_when_failed(_inject_mock_prefect) -> None:
    _inject_mock_prefect(
        {"state_type": "FAILED", "state_message": "connection refused"}
    )

    with TestClient(app) as client:
        body = _consume_sse(client, "/api/v1/sc/import/test-id/stream")
        assert "event: error" in body
        assert "connection refused" in body


def test_sse_emits_progress_when_running(_inject_mock_prefect) -> None:
    _inject_mock_prefect(
        {"state_type": "RUNNING", "state_message": ""},
        {"state_type": "COMPLETED", "state_message": ""},
    )

    with TestClient(app) as client:
        body = _consume_sse(client, "/api/v1/sc/import/test-id/stream")
        assert "event: progress" in body
        assert "running" in body
        assert "event: done" in body
