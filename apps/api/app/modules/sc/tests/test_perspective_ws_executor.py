from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, cast

import polars as pl
import pytest

from app.modules.sc.port.http.perspective_ws import (
    _empty_samples_df,
    _load_initial_samples,
    _run_serialized_perspective_handler,
)


@pytest.mark.asyncio
async def test_initial_perspective_update_runs_off_the_event_loop_thread() -> None:
    event_loop_thread = threading.get_ident()
    update_threads: list[int] = []

    class FakeTable:
        def update(self, _data: pl.DataFrame) -> None:
            update_threads.append(threading.get_ident())

    async def samples_df_factory() -> pl.DataFrame:
        return _empty_samples_df()

    executor = ThreadPoolExecutor(max_workers=1)
    try:
        await _load_initial_samples(
            websocket=cast(Any, object()),
            joined_table=cast(Any, FakeTable()),
            samples_df_factory=samples_df_factory,
            stop_event=asyncio.Event(),
            update_lock=asyncio.Lock(),
            executor=executor,
        )
    finally:
        await asyncio.to_thread(executor.shutdown, wait=True)

    assert len(update_threads) == 1
    assert update_threads[0] != event_loop_thread


@pytest.mark.asyncio
async def test_perspective_response_backlog_is_bounded() -> None:
    send_started = asyncio.Event()
    release_send = asyncio.Event()
    close_codes: list[int] = []

    class FakeWebSocket:
        async def accept(self) -> None:
            return None

        async def receive(self) -> dict[str, bytes]:
            return {"bytes": b"request"}

        def _raise_on_disconnect(self, _message: dict[str, bytes]) -> None:
            return None

        async def send_bytes(self, _message: bytes) -> None:
            send_started.set()
            await release_send.wait()

        async def close(self, code: int) -> None:
            close_codes.append(code)

    class FakeSession:
        def __init__(self, enqueue_response: Any) -> None:
            self._enqueue_response = enqueue_response

        def handle_request(self, _payload: bytes) -> None:
            for _ in range(32):
                self._enqueue_response(b"x")

        def close(self) -> None:
            return None

    class FakeServer:
        def new_session(self, enqueue_response: Any) -> FakeSession:
            return FakeSession(enqueue_response)

    executor = ThreadPoolExecutor(max_workers=1)
    task = asyncio.create_task(
        _run_serialized_perspective_handler(
            server=cast(Any, FakeServer()),
            websocket=cast(Any, FakeWebSocket()),
            executor=executor,
        )
    )
    try:
        await asyncio.wait_for(send_started.wait(), timeout=1)
        release_send.set()
        await asyncio.wait_for(task, timeout=1)
    finally:
        release_send.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.to_thread(executor.shutdown, wait=True)

    assert close_codes == [1013]
