from __future__ import annotations

import asyncio
import threading
from typing import Any, cast
from unittest.mock import AsyncMock

from sc_upstream.server import _shutdown_servers


class _BlockingFlightServer:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def shutdown(self) -> None:
        self.started.set()
        self.release.wait()


def test_shutdown_does_not_wait_for_blocking_flight_requests() -> None:
    grpc_server = AsyncMock()
    flight_server = _BlockingFlightServer()

    asyncio.run(_shutdown_servers(cast(Any, grpc_server), cast(Any, flight_server)))

    assert flight_server.started.wait(timeout=1)
    grpc_server.stop.assert_awaited_once_with(0)
    flight_server.release.set()
