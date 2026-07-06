from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as redis_client  # type: ignore[import-untyped]
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.composition import build_app_context
from app.core.config import load_config
from app.core.logger import init_logging
from app.modules.sc.port.http.perspective_router import router
from app.shared.infrastructure.redis.event_publisher import RedisEventPublisher
import app.registrations as _registrations  # noqa: F401

_logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(ws_app: FastAPI):
    cfg = load_config()
    init_logging(cfg)
    ctx = build_app_context(cfg)
    ws_app.state.app_context = ctx

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
        prefect_close = getattr(ctx.shared.prefect_client, "close", None)
        if prefect_close is not None:
            await prefect_close()
        await ctx.shared.db_engine.dispose()


app = FastAPI(
    title="Online Finetune Perspective WebSocket",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", response_model=None)
async def readiness(request: Request) -> dict[str, str] | JSONResponse:
    try:
        async with (
            request.app.state.app_context.shared.db_engine.connect() as connection
        ):
            await connection.execute(text("SELECT 1"))
    except Exception:
        _logger.warning("Readiness check failed: database unavailable", exc_info=True)
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ready"}
