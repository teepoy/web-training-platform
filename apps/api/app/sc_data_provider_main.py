from __future__ import annotations

import asyncio
import logging
import math
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

import redis.asyncio as redis_client  # type: ignore[import-untyped]
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import ScDataProviderConfig, load_config
from app.core.logger import init_logging
from app.modules.dataset_collections.port.local import (
    DatasetCollectionRevisionReaderPort,
)
from app.modules.auth.app.services.dev_auth_context import load_dev_auth_context
from app.modules.sc.data_provider.cache import ScDataObjectCache
from app.modules.sc.data_provider.engine import DuckDbQueryExecutor
from app.modules.sc.data_provider.materializer import ScDataMaterializer
from app.modules.sc.data_provider.revision import ScDataRevisionStore
from app.modules.sc.data_provider.router import (
    ScDataProviderRedis,
    ScDataProviderRuntime,
    router,
)
from app.modules.sc.domain.upstream_reader import ScUpstreamReader
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.shared.domain.protocols import ArtifactStorage
from app.sc_data_provider_composition import (
    build_sc_data_provider_app_context,
    close_sc_data_provider_app_context,
)


_logger = logging.getLogger(__name__)


def _validate_data_provider_config(config: ScDataProviderConfig) -> None:
    if config.implementation != "duckdb":
        raise RuntimeError(
            "app.sc_data_provider_main requires "
            "SC_DATA_PROVIDER_IMPLEMENTATION=duckdb; automatic fallback is forbidden"
        )
    positive_fields = (
        "max_rss_mb",
        "duckdb_threads",
        "connection_recycle_rss_mb",
        "worker_count",
        "container_memory_limit_mb",
        "python_overhead_mb",
        "service_headroom_mb",
        "object_cache_max_bytes",
        "object_cache_low_watermark_bytes",
        "object_idle_ttl_seconds",
        "cleanup_interval_seconds",
        "stale_write_seconds",
        "lease_ttl_seconds",
        "lease_heartbeat_seconds",
        "build_lock_ttl_seconds",
        "build_lock_heartbeat_seconds",
        "build_wait_timeout_seconds",
        "build_poll_interval_ms",
        "sql_timeout_seconds",
        "max_response_bytes",
        "arrow_batch_rows",
        "stream_queue_capacity",
        "stream_queue_poll_interval_ms",
        "sse_heartbeat_seconds",
        "sse_max_connection_seconds",
    )
    for field_name in positive_fields:
        if int(getattr(config, field_name)) <= 0:
            raise RuntimeError(
                f"sc.data_provider.{field_name} must be greater than zero"
            )
    if config.duckdb_threads != 1:
        raise RuntimeError("sc.data_provider.duckdb_threads must be 1 per worker")
    if config.connection_recycle_rss_mb >= config.max_rss_mb:
        raise RuntimeError(
            "sc.data_provider.connection_recycle_rss_mb must be below max_rss_mb"
        )
    if config.object_cache_low_watermark_bytes >= config.object_cache_max_bytes:
        raise RuntimeError(
            "sc.data_provider.object_cache_low_watermark_bytes must be below "
            "object_cache_max_bytes"
        )
    if config.lease_heartbeat_seconds >= config.lease_ttl_seconds:
        raise RuntimeError(
            "sc.data_provider.lease_heartbeat_seconds must be below lease_ttl_seconds"
        )
    if config.build_lock_heartbeat_seconds >= config.build_lock_ttl_seconds:
        raise RuntimeError(
            "sc.data_provider.build_lock_heartbeat_seconds must be below "
            "build_lock_ttl_seconds"
        )
    duckdb_memory_mb = _parse_memory_mb(config.duckdb_memory_limit)
    required_mb = (
        config.worker_count * (duckdb_memory_mb + config.python_overhead_mb)
        + config.service_headroom_mb
    )
    if required_mb > config.container_memory_limit_mb:
        raise RuntimeError(
            "SC data-provider capacity exceeds its container limit: "
            f"workers={config.worker_count}, duckdb_memory_mb={duckdb_memory_mb}, "
            f"python_overhead_mb={config.python_overhead_mb}, "
            f"service_headroom_mb={config.service_headroom_mb}, "
            f"required_mb={required_mb}, "
            f"container_memory_limit_mb={config.container_memory_limit_mb}"
        )


_MEMORY_PATTERN = re.compile(
    r"^(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>B|KB|KiB|MB|MiB|GB|GiB|TB|TiB)$",
    re.IGNORECASE,
)


def _parse_memory_mb(value: str) -> int:
    match = _MEMORY_PATTERN.fullmatch(value.strip())
    if match is None:
        raise RuntimeError(f"invalid memory size: {value!r}")
    amount = float(match.group("amount"))
    unit = match.group("unit").lower()
    bytes_per_unit = {
        "b": 1,
        "kb": 1_000,
        "kib": 1_024,
        "mb": 1_000_000,
        "mib": 1_048_576,
        "gb": 1_000_000_000,
        "gib": 1_073_741_824,
        "tb": 1_000_000_000_000,
        "tib": 1_099_511_627_776,
    }[unit]
    return math.ceil(amount * bytes_per_unit / 1_048_576)


@asynccontextmanager
async def lifespan(data_app: FastAPI):
    config = load_config()
    init_logging(config)
    provider_config = config.sc.data_provider
    _validate_data_provider_config(provider_config)
    context = build_sc_data_provider_app_context(config)
    data_app.state.app_context = context
    data_app.state.dev_auth_context = None
    redis = cast(
        ScDataProviderRedis,
        redis_client.Redis(
            host=str(config.redis.host),
            port=int(config.redis.port),
            password=str(config.redis.password) if config.redis.password else None,
            db=int(config.redis.db),
            socket_connect_timeout=1,
            socket_timeout=None,
        ),
    )
    await redis.ping()
    cache = ScDataObjectCache(redis, config=provider_config)
    await cache.initialize()
    revisions = ScDataRevisionStore(redis, namespace=provider_config.revision_namespace)
    materializer = ScDataMaterializer(
        upstream_reader=context.injector.get(ScUpstreamReader),
        storage_factory=context.injector.get(DatasetStorageFactoryPort),
        collection_revision_reader=context.injector.get(
            DatasetCollectionRevisionReaderPort
        ),
        artifact_storage=context.injector.get(ArtifactStorage),
        cache=cache,
        batch_rows=provider_config.arrow_batch_rows,
    )
    executor = DuckDbQueryExecutor(config=provider_config)
    data_app.state.sc_data_provider = ScDataProviderRuntime(
        config=provider_config,
        redis=redis,
        cache=cache,
        revisions=revisions,
        materializer=materializer,
        executor=executor,
    )
    cleanup_stop = asyncio.Event()
    cleanup_task = asyncio.create_task(
        cache.run_cleanup_loop(cleanup_stop),
        name="sc-data-provider-cache-cleanup",
    )
    try:
        async with context.shared.db_engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        if not bool(getattr(config.auth, "enabled", True)):
            data_app.state.dev_auth_context = await load_dev_auth_context(
                context.shared.session_factory
            )
        yield
    finally:
        data_app.state.dev_auth_context = None
        cleanup_stop.set()
        await cleanup_task
        await executor.close()
        await redis.aclose()
        await close_sc_data_provider_app_context(context)


app = FastAPI(
    title="Online Finetune SC Data Provider",
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/health")
def health(request: Request) -> dict[str, str | float | int]:
    rss_mb = _record_memory_usage(request, endpoint="/health")
    runtime = _runtime(request)
    return {
        "status": "ok",
        "rss_mb": rss_mb,
        "duckdb_temp_bytes": runtime.executor.temp_directory_size_bytes(),
        "worker_pid": os.getpid(),
    }


@app.get("/ready", response_model=None)
async def readiness(request: Request) -> dict[str, str | float | int] | JSONResponse:
    try:
        rss_mb = _record_memory_usage(request, endpoint="/ready")
        runtime = _runtime(request)
        if rss_mb >= runtime.config.max_rss_mb:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unavailable",
                    "reason": "memory_pressure",
                    "rss_mb": rss_mb,
                    "max_rss_mb": runtime.config.max_rss_mb,
                },
            )
        await runtime.redis.ping()
        async with (
            request.app.state.app_context.shared.db_engine.connect() as connection
        ):
            await connection.execute(text("SELECT 1"))
    except Exception:
        _logger.warning("SC data-provider readiness check failed", exc_info=True)
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {
        "status": "ready",
        "rss_mb": rss_mb,
        "duckdb_temp_bytes": runtime.executor.temp_directory_size_bytes(),
        "worker_pid": os.getpid(),
    }


def _record_memory_usage(request: Request, *, endpoint: str) -> float:
    rss_mb = _current_rss_mb()
    runtime = _runtime(request)
    _logger.info(
        "SC data-provider memory usage endpoint=%s rss_mb=%.1f max_rss_mb=%d",
        endpoint,
        rss_mb,
        runtime.config.max_rss_mb,
    )
    return rss_mb


def _current_rss_mb(status_path: Path = Path("/proc/self/status")) -> float:
    for line in status_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024
    raise RuntimeError(f"VmRSS was not found in {status_path}")


def _runtime(request: Request) -> ScDataProviderRuntime:
    runtime = getattr(request.app.state, "sc_data_provider", None)
    if runtime is None:
        raise RuntimeError("SC data-provider runtime was not initialized")
    return runtime
