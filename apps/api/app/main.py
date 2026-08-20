from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select, text
from starlette.routing import compile_path

from app.composition import build_app_context
from app.modules.auth.app.services.auth_service import decode_access_token
from app.modules.auth.app.services.dev_auth_context import load_dev_auth_context
from app.modules.auth.port.http.deps import (
    get_current_org,
    get_current_user,
    require_superadmin,
)
from app.modules.dashboard.port.http.deps import DashboardServiceDep
from app.modules.training.app.services.status_reconciler import (
    TrainingStatusReconciler,
)
from app.shared.api.schemas import (
    DashboardResponse,
)
from app.core.config import load_config
from app.core.logger import init_logging
from app.core.platform_setup import validate_platform_dependencies
from app.shared.db.session import init_db
from app.shared.db.registry import UserORM
from app.shared.infrastructure.metrics import online_jwt_users
from app.shared.infrastructure.redis.event_publisher import RedisEventPublisher
from app.shared.api.schemas import Organization, User
from app.modules.registry import EXTENSION_ROUTERS, MODULE_ROUTERS
import app.registrations as _registrations  # noqa: F401

_logger = logging.getLogger(__name__)


def _strip_api_prefix(router: Any) -> None:
    for route in router.routes:
        path = getattr(route, "path", "")
        if path == "/api/v1":
            new_path = ""
        elif path.startswith("/api/v1/"):
            new_path = path.removeprefix("/api/v1")
        else:
            continue
        route.path = new_path
        route.path_regex, route.path_format, route.param_convertors = compile_path(
            new_path
        )


@asynccontextmanager
async def lifespan(api: FastAPI):
    cfg = load_config()
    init_logging(cfg)
    ctx = build_app_context(cfg)
    if ctx.injector is None:
        raise RuntimeError("AppContext injector was not initialized")
    training_status_reconciler = ctx.injector.get(TrainingStatusReconciler)
    api.state.app_context = ctx
    import redis.asyncio as redis_client  # type: ignore[import-untyped]

    metrics_redis: Any | None = None
    api.state.startup_ready = False
    api.state.metrics_redis = None
    api.state.dev_auth_context = None
    try:
        if bool(cfg.db.auto_create):
            await init_db(ctx.shared.db_engine)

        if str(cfg.app.env) == "test":
            online_jwt_users.configure_redis(None)
            ctx.shared.redis_event_publisher = RedisEventPublisher(None)
            _logger.info("Redis and external startup checks disabled for test profile")
        else:
            timeout = float(cfg.startup_checks.dependency_timeout_seconds)
            metrics_redis = redis_client.Redis(
                host=str(cfg.redis.host),
                port=int(cfg.redis.port),
                password=str(cfg.redis.password) if cfg.redis.password else None,
                db=int(cfg.redis.db),
                socket_connect_timeout=timeout,
                socket_timeout=timeout,
            )
            await metrics_redis.ping()  # type: ignore[awaitable]
            online_jwt_users.configure_redis(metrics_redis)
            ctx.shared.redis_event_publisher = RedisEventPublisher(
                metrics_redis,
                revision_namespace=cfg.sc.data_provider.revision_namespace,
            )
            _logger.info("Metrics Redis + event publisher configured")
            api.state.metrics_redis = metrics_redis
            await validate_platform_dependencies(cfg, ctx.shared)

        if not bool(getattr(cfg.auth, "enabled", True)):
            _logger.info("auth disabled — loading prepared dev auth context")
            api.state.dev_auth_context = await load_dev_auth_context(
                ctx.shared.session_factory
            )

        if ctx.jobs is None:
            raise RuntimeError("AppContext jobs module was not initialized")

        try:
            sensor_count = ctx.jobs.sensors.sensor_registry.load()
        except Exception:
            sensor_count = 0
        _logger.info("Sensor registry: %d sensors loaded", sensor_count)

        if str(cfg.execution.engine) == "prefect":
            training_status_reconciler.start()

        api.state.startup_ready = True
        yield
    finally:
        api.state.startup_ready = False
        api.state.dev_auth_context = None
        await training_status_reconciler.stop()
        await online_jwt_users.close()
        if metrics_redis is not None and api.state.metrics_redis is None:
            await metrics_redis.aclose()
        online_jwt_users.configure_redis(None)
        api.state.metrics_redis = None
        prefect_close = getattr(ctx.shared.prefect_client, "close", None)
        if prefect_close is not None:
            await prefect_close()
        await ctx.shared.db_engine.dispose()


app = FastAPI(title="Online Finetune API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def collect_online_jwt_users(request: Request, call_next: Any) -> Response:
    token: str | None = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    elif "token" in request.query_params:
        token = request.query_params["token"]

    if token and not token.startswith("ftp_"):
        try:
            payload = decode_access_token(token)
            user_id = payload.get("sub")
            if isinstance(user_id, str):
                email = payload.get("email")
                name = payload.get("name")
                await online_jwt_users.observe_user(
                    user_id,
                    email=email if isinstance(email, str) else None,
                    name=name if isinstance(name, str) else None,
                )
        except Exception:
            pass

    response = await call_next(request)
    return response


for r in [*MODULE_ROUTERS, *EXTENSION_ROUTERS]:
    _strip_api_prefix(r)
    app.include_router(r, prefix="/api/v1")


# ---------------------------------------------------------------------------
# Core endpoints not belonging to a single domain
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(
        content=await online_jwt_users.render_prometheus(),
        media_type=online_jwt_users.content_type,
    )


@app.get("/api/v1/metrics/users/daily", include_in_schema=False)
async def daily_user_metrics(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    await require_superadmin(current_user=current_user)
    observed_users = await online_jwt_users.daily_users()
    user_ids = [user.id for user in observed_users]
    users_by_id: dict[str, UserORM] = {}
    if user_ids:
        session_factory = request.app.state.app_context.shared.session_factory
        async with session_factory() as session:
            result = await session.execute(
                select(UserORM).where(UserORM.id.in_(user_ids))
            )
            users_by_id = {user.id: user for user in result.scalars().all()}

    details: list[dict[str, str | None]] = []
    for observed in observed_users:
        user = users_by_id.get(observed.id)
        details.append(
            {
                "id": observed.id,
                "email": user.email if user is not None else observed.email,
                "name": user.name if user is not None else observed.name,
                "first_seen_at": observed.first_seen_at,
                "last_seen_at": observed.last_seen_at,
            }
        )
    return {"count": len(details), "users": details}


@app.get(
    "/ready",
    response_model=dict[str, str],
    responses={503: {"description": "Database unavailable"}},
)
async def readiness(request: Request) -> dict[str, str] | JSONResponse:
    try:
        if not bool(getattr(request.app.state, "startup_ready", False)):
            raise RuntimeError("startup validation has not completed")
        async with (
            request.app.state.app_context.shared.db_engine.connect() as connection
        ):
            await connection.execute(text("SELECT 1"))
        metrics_redis = getattr(request.app.state, "metrics_redis", None)
        cfg = request.app.state.app_context.shared.config
        if str(cfg.app.env) != "test":
            if metrics_redis is None:
                raise RuntimeError("Redis client is not configured")
            await metrics_redis.ping()
    except Exception:
        _logger.warning("Readiness check failed", exc_info=True)
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable"},
        )
    return {"status": "ready"}


@app.get("/api/v1/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    service: DashboardServiceDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> DashboardResponse:
    return await service.get_dashboard_data(org_id=org.id)
