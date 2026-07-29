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
