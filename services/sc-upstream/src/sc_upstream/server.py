from __future__ import annotations

import asyncio
import logging
import os
import signal
import threading

import grpc

from proto_stubs.sc.v1 import upstream_pb2_grpc as pb_grpc

from .cache import QueryCache
from .flight_server import UpstreamFlightServer
from .service import ScUpstreamService
from .upstream_db import create_mock_inspection_zips_db, create_mock_upstream_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def serve() -> None:
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

    gserver = grpc.aio.server()
    pb_grpc.add_ScUpstreamServicer_to_server(
        ScUpstreamService(upstream, zips, cache), gserver
    )
    gserver.add_insecure_port(f"[::]:{grpc_port}")
    logger.info("sc-upstream gRPC server starting on :%s", grpc_port)
    await gserver.start()

    flight_location = f"grpc://0.0.0.0:{flight_port}"
    flight_server = UpstreamFlightServer(upstream, cache, location=flight_location)
    flight_thread = threading.Thread(target=flight_server.serve, daemon=True)
    flight_thread.start()
    logger.info("sc-upstream Arrow Flight server starting on :%s", flight_port)

    stop_event = asyncio.Event()

    def _handle_signal() -> None:
        logger.info("shutting down...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _handle_signal())

    await stop_event.wait()
    await gserver.stop(0)
    flight_server.shutdown()
    flight_thread.join(timeout=30)


if __name__ == "__main__":
    asyncio.run(serve())
