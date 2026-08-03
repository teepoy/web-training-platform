from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import redis.asyncio as redis_client  # type: ignore[import-untyped]
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from perspective import Server
from sqlalchemy import text

from app.core.config import load_config
from app.core.logger import init_logging
from app.modules.sc.port.http.perspective_router import router
from app.perspective_composition import (
    build_perspective_app_context,
    close_perspective_app_context,
)
from app.shared.infrastructure.redis.event_publisher import RedisEventPublisher

_logger = logging.getLogger(__name__)

_MAX_RSS_ENV = "PERSPECTIVE_WS_MAX_RSS_MB"


def _current_rss_mb(status_path: Path = Path("/proc/self/status")) -> float:
    for line in status_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("VmRSS:"):
            rss_kib = int(line.split()[1])
            return rss_kib / 1024
    raise RuntimeError(f"VmRSS was not found in {status_path}")


def _configured_max_rss_mb() -> float | None:
    raw_limit = os.environ.get(_MAX_RSS_ENV)
    if raw_limit is None:
        return None
    limit = float(raw_limit)
    if limit <= 0:
        raise ValueError(f"{_MAX_RSS_ENV} must be greater than zero")
    return limit


def _record_memory_usage(*, endpoint: str) -> tuple[float, float | None]:
    rss_mb = _current_rss_mb()
    max_rss_mb = _configured_max_rss_mb()
    _logger.info(
        "Perspective memory usage endpoint=%s rss_mb=%.1f max_rss_mb=%s",
        endpoint,
        rss_mb,
        f"{max_rss_mb:.1f}" if max_rss_mb is not None else "disabled",
    )
    return rss_mb, max_rss_mb


@asynccontextmanager
async def lifespan(ws_app: FastAPI):
    cfg = load_config()
    init_logging(cfg)
    ctx = build_perspective_app_context(cfg)
    ws_app.state.app_context = ctx
    ws_app.state.perspective_server = Server()

    redis: Any = redis_client.Redis(
        host=str(cfg.redis.host),
        port=int(cfg.redis.port),
        password=str(cfg.redis.password) if cfg.redis.password else None,
        db=int(cfg.redis.db),
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    await redis.ping()
    ctx.shared.redis_event_publisher = RedisEventPublisher(redis)

    try:
        async with ctx.shared.db_engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        yield
    finally:
        await redis.aclose()
        await close_perspective_app_context(ctx)


app = FastAPI(
    title="Online Finetune Perspective WebSocket",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    try:
        _record_memory_usage(endpoint="/health")
    except (OSError, RuntimeError, ValueError):
        _logger.exception("Health check failed to record Perspective memory usage")
    return {"status": "ok"}


@app.get("/ready", response_model=None)
async def readiness(request: Request) -> dict[str, str] | JSONResponse:
    try:
        rss_mb, max_rss_mb = _record_memory_usage(endpoint="/ready")
        if max_rss_mb is not None and rss_mb >= max_rss_mb:
            _logger.error(
                "Readiness check failed: RSS %.1f MiB reached %.1f MiB limit",
                rss_mb,
                max_rss_mb,
            )
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unavailable",
                    "reason": "memory_pressure",
                },
            )
    except (OSError, RuntimeError, ValueError):
        _logger.exception("Readiness check failed: invalid RSS health configuration")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "reason": "memory_healthcheck_failed",
            },
        )

    try:
        async with (
            request.app.state.app_context.shared.db_engine.connect() as connection
        ):
            await connection.execute(text("SELECT 1"))
    except Exception:
        _logger.warning("Readiness check failed: database unavailable", exc_info=True)
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ready"}
