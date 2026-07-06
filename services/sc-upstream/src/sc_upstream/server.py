from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from collections.abc import Awaitable, Callable
from typing import Any

import grpc
import uvicorn

from proto_stubs.sc.v1 import upstream_pb2_grpc as pb_grpc

from .cache import QueryCache
from .flight_server import UpstreamFlightServer
from .service import ScUpstreamService
from .upstream_db import create_mock_inspection_zips_db, create_mock_upstream_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]


class ScUpstreamRuntime:
    def __init__(self) -> None:
        self._grpc_server: grpc.aio.Server | None = None
        self._flight_server: UpstreamFlightServer | None = None
        self._flight_thread: threading.Thread | None = None

    async def start(self) -> None:
        upstream_db_url = os.environ.get(
            "UPSTREAM_DB_URL", "sqlite:///./wafer_inspection.db"
        )
        zips_db_url = os.environ.get("ZIPS_DB_URL", "sqlite:///./inspection_zips.db")
        grpc_port = os.environ.get("GRPC_PORT", "9091")
        flight_port = os.environ.get("FLIGHT_PORT", "9093")
        cache_dir = os.environ.get("CACHE_DIR", "/tmp/sc-upstream")

        logger.info("connecting to upstream db")
        upstream = create_mock_upstream_db(db_url=upstream_db_url)
        logger.info("connecting to zips db")
        zips = create_mock_inspection_zips_db(db_url=zips_db_url)
        logger.info("cache dir: %s", cache_dir)
        cache = QueryCache(cache_dir=cache_dir)

        grpc_server = grpc.aio.server()
        pb_grpc.add_ScUpstreamServicer_to_server(
            ScUpstreamService(upstream, zips, cache), grpc_server
        )
        grpc_server.add_insecure_port(f"[::]:{grpc_port}")
        logger.info("sc-upstream gRPC server starting on :%s", grpc_port)
        await grpc_server.start()

        flight_location = f"grpc://0.0.0.0:{flight_port}"
        flight_server = UpstreamFlightServer(upstream, cache, location=flight_location)
        flight_thread = threading.Thread(target=flight_server.serve, daemon=True)
        flight_thread.start()
        logger.info("sc-upstream Arrow Flight server starting on :%s", flight_port)

        self._grpc_server = grpc_server
        self._flight_server = flight_server
        self._flight_thread = flight_thread

    async def stop(self) -> None:
        logger.info("shutting down sc-upstream runtime")
        if self._grpc_server is not None:
            await self._grpc_server.stop(grace=30)
            self._grpc_server = None
        if self._flight_server is not None:
            self._flight_server.shutdown()
            self._flight_server = None
        if self._flight_thread is not None:
            self._flight_thread.join(timeout=30)
            self._flight_thread = None


class ScUpstreamApp:
    def __init__(self) -> None:
        self._runtime = ScUpstreamRuntime()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self._handle_lifespan(receive, send)
            return
        if scope["type"] != "http":
            await self._send_response(send, 404, {"error": "not found"})
            return

        path = scope.get("path", "")
        if path in {"/health", "/ready"}:
            await self._send_response(send, 200, {"status": "ok"})
            return
        await self._send_response(send, 404, {"error": "not found"})

    async def _handle_lifespan(self, receive: Receive, send: Send) -> None:
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                try:
                    await self._runtime.start()
                except Exception as exc:
                    await send(
                        {
                            "type": "lifespan.startup.failed",
                            "message": str(exc),
                        }
                    )
                    raise
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await self._runtime.stop()
                await send({"type": "lifespan.shutdown.complete"})
                return

    async def _send_response(
        self,
        send: Send,
        status: int,
        payload: dict[str, str],
    ) -> None:
        body = json.dumps(payload).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


app = ScUpstreamApp()


async def serve() -> None:
    config = uvicorn.Config(
        "sc_upstream.server:app",
        host=os.environ.get("HEALTH_HOST", "0.0.0.0"),
        port=int(os.environ.get("HEALTH_PORT", "8091")),
        log_level=os.environ.get("UVICORN_LOG_LEVEL", "info"),
        timeout_keep_alive=int(os.environ.get("UVICORN_TIMEOUT_KEEP_ALIVE", "120")),
        timeout_graceful_shutdown=int(
            os.environ.get("UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN", "600")
        ),
        timeout_worker_healthcheck=int(
            os.environ.get("UVICORN_TIMEOUT_WORKER_HEALTHCHECK", "60")
        ),
    )
    server = uvicorn.Server(config)
    await server.serve()


def main() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    main()
