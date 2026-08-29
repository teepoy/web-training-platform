from __future__ import annotations

import asyncio
from dataclasses import dataclass
import importlib
import logging
import os
import signal
import threading
from typing import Callable, cast

import grpc

from proto_stubs.sc.v1 import upstream_pb2_grpc as pb_grpc

from .cache import QueryCache
from .direct_cache import DirectMetadataCache
from .flight_server import UpstreamFlightServer
from .service import ScUpstreamService
from .upstream_db import InspectionZipsDB, UpstreamDB

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AdapterFactory = Callable[[], tuple[UpstreamDB, InspectionZipsDB]]


@dataclass(frozen=True)
class RunningUpstreamServers:
    grpc_server: grpc.aio.Server
    flight_server: UpstreamFlightServer

    async def stop(self) -> None:
        await _shutdown_servers(self.grpc_server, self.flight_server)


async def _shutdown_servers(
    gserver: grpc.aio.Server, flight_server: UpstreamFlightServer
) -> None:
    # Flight shutdown blocks until in-flight requests finish. Keep it off the
    # asyncio loop and use a daemon thread so a development reload is not held
    # beyond the watcher's process grace period.
    threading.Thread(
        target=flight_server.shutdown,
        name="sc-upstream-flight-shutdown",
        daemon=True,
    ).start()
    await gserver.stop(0)


async def start_servers(
    *,
    upstream: UpstreamDB,
    zips: InspectionZipsDB,
    metadata_cache: QueryCache | DirectMetadataCache,
    flight_cache: QueryCache | None,
    grpc_port: int,
    flight_port: int,
) -> RunningUpstreamServers:
    gserver = grpc.aio.server()
    pb_grpc.add_ScUpstreamServicer_to_server(
        ScUpstreamService(upstream, zips, metadata_cache), gserver
    )
    gserver.add_insecure_port(f"[::]:{grpc_port}")
    await gserver.start()

    flight_server = UpstreamFlightServer(
        upstream,
        flight_cache,
        location=f"grpc://0.0.0.0:{flight_port}",
    )
    flight_thread = threading.Thread(target=flight_server.serve, daemon=True)
    flight_thread.start()
    return RunningUpstreamServers(
        grpc_server=gserver,
        flight_server=flight_server,
    )


def _load_adapter_factory(reference: str) -> AdapterFactory:
    module_name, separator, attribute_name = reference.partition(":")
    if not separator or not module_name or not attribute_name:
        raise RuntimeError(
            "SC_UPSTREAM_ADAPTER_FACTORY must use 'module.path:factory_name'"
        )
    module = importlib.import_module(module_name)
    factory = getattr(module, attribute_name, None)
    if not callable(factory):
        raise RuntimeError(
            f"SC_UPSTREAM_ADAPTER_FACTORY does not resolve to a callable: {reference}"
        )
    return cast(AdapterFactory, factory)


async def serve() -> None:
    factory_reference = os.environ.get("SC_UPSTREAM_ADAPTER_FACTORY")
    if not factory_reference:
        raise RuntimeError("SC_UPSTREAM_ADAPTER_FACTORY is required")
    grpc_port = int(os.environ["GRPC_PORT"])
    flight_port = int(os.environ["FLIGHT_PORT"])
    cache_dir = os.environ["CACHE_DIR"]

    upstream, zips = _load_adapter_factory(factory_reference)()
    cache = QueryCache(cache_dir=cache_dir)
    running = await start_servers(
        upstream=upstream,
        zips=zips,
        metadata_cache=cache,
        flight_cache=cache,
        grpc_port=grpc_port,
        flight_port=flight_port,
    )
    logger.info("sc-upstream gRPC server started on :%s", grpc_port)
    logger.info("sc-upstream Arrow Flight server started on :%s", flight_port)

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
    await running.stop()


if __name__ == "__main__":
    asyncio.run(serve())
