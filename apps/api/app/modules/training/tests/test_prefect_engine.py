from __future__ import annotations

from unittest.mock import AsyncMock, Mock, call, patch

import pytest

from app.modules.training.adapter.engines.prefect_engine import PrefectWorkPoolEngine


@pytest.mark.asyncio
async def test_prefect_event_stream_fetches_only_new_log_pages() -> None:
    client = Mock()
    client.get_flow_run = AsyncMock(
        side_effect=[
            {"parameters": {"job_id": "job-1"}},
            {"state": {"type": "RUNNING"}},
            {"state": {"type": "COMPLETED"}},
            {"state": {"type": "COMPLETED", "data": {}}},
        ]
    )
    client.get_flow_run_logs = AsyncMock(
        side_effect=[
            [{"message": "first", "level": 20}],
            [{"message": "second", "level": 20}],
        ]
    )
    engine = PrefectWorkPoolEngine(client)

    with patch(
        "app.modules.training.adapter.engines.prefect_engine.asyncio.sleep",
        new_callable=AsyncMock,
    ):
        events = [event async for event in engine.stream_events("run-1")]

    assert [event.message for event in events if "log_level" in event.payload] == [
        "first",
        "second",
    ]
    assert client.get_flow_run_logs.await_args_list == [
        call("run-1", limit=200, offset=0),
        call("run-1", limit=200, offset=1),
    ]
