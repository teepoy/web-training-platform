from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import polars as pl
import pytest
from starlette.websockets import WebSocketDisconnect

from app.modules.sc.port.http import perspective_ws


class _FakeWebSocket:
    def __init__(self, messages: list[dict[str, Any]]) -> None:
        self._messages = iter(messages)
        self.accepted = False
        self.sent: list[bytes] = []
        self.close_codes: list[int] = []

    async def accept(self) -> None:
        self.accepted = True

    async def receive(self) -> dict[str, Any]:
        await asyncio.sleep(0)
        return next(self._messages)

    def _raise_on_disconnect(self, message: dict[str, Any]) -> None:
        if message["type"] == "websocket.disconnect":
            raise WebSocketDisconnect(message.get("code", 1000))

    async def send_bytes(self, message: bytes) -> None:
        self.sent.append(message)

    async def close(self, code: int) -> None:
        self.close_codes.append(code)


class _FakeSession:
    def __init__(self, response: Callable[[bytes], None]) -> None:
        self._response = response
        self.requests: list[bytes] = []
        self.closed = False

    def handle_request(self, message: bytes) -> None:
        self.requests.append(message)
        self._response(b"response:" + message)

    def close(self) -> None:
        self.closed = True


class _FakeServer:
    def __init__(self) -> None:
        self.session: _FakeSession | None = None

    def new_session(self, response: Callable[[bytes], None]) -> _FakeSession:
        self.session = _FakeSession(response)
        return self.session


@pytest.mark.asyncio
async def test_serialized_handler_waits_for_requests_and_closes_session() -> None:
    websocket = _FakeWebSocket(
        [
            {"type": "websocket.receive", "bytes": b"request"},
            {"type": "websocket.disconnect", "code": 1000},
        ]
    )
    server = _FakeServer()
    executor = ThreadPoolExecutor(max_workers=1)

    try:
        await perspective_ws._run_serialized_perspective_handler(
            server=server,  # type: ignore[arg-type]
            websocket=websocket,  # type: ignore[arg-type]
            executor=executor,
        )
    finally:
        executor.shutdown(wait=True)

    assert websocket.accepted
    assert websocket.sent == [b"response:request"]
    assert server.session is not None
    assert server.session.requests == [b"request"]
    assert server.session.closed


@pytest.mark.asyncio
async def test_run_ws_deletes_table_and_terminates_local_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cleanup_order: list[str] = []

    class FakeTable:
        def delete(self) -> None:
            cleanup_order.append("table")

    class FakeClient:
        def terminate(self) -> None:
            cleanup_order.append("client")

    async def stop_handler(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(
        perspective_ws,
        "_init_tables",
        lambda _server, _df, *, table_name: (FakeClient(), FakeTable()),
    )
    monkeypatch.setattr(
        perspective_ws,
        "_run_serialized_perspective_handler",
        stop_handler,
    )

    async def samples_df_factory() -> pl.DataFrame:
        return perspective_ws._empty_samples_df()

    await perspective_ws.run_sc_perspective_ws(
        server=object(),  # type: ignore[arg-type]
        table_name="5b175f27-69d0-4d3d-a43e-48e372b085f7",
        websocket=object(),  # type: ignore[arg-type]
        dataset_id=None,
        samples_df_factory=samples_df_factory,
        redis_client=None,
    )

    assert cleanup_order == ["table", "client"]
