from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select, text
from starlette.routing import compile_path

from app.composition import build_app_context
from app.modules.auth.app.services.auth_service import decode_access_token
from app.modules.auth.port.http.deps import (
    get_current_org,
    get_current_user,
    require_superadmin,
    seed_dev_auth_context,
)
from app.modules.dashboard.port.http.deps import DashboardServiceDep
from app.shared.api.schemas import (
    DashboardResponse,
)
from app.core.config import load_config
from app.core.logger import init_logging
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


async def _ensure_prefect_deployments(cfg: Any, prefect_client: Any) -> None:
    engine = str(cfg.execution.engine)
    if engine != "prefect":
        return

    _logger.info("Ensuring Prefect deployments (execution.engine=prefect)")

    deployments = [
        # ── GPU pool ──
        {
            "deployment_name": "train-job-deployment",
            "flow_name": "training-train-job",
            "work_pool_name": "default-gpu",
            "entrypoint": "app.modules.training.flows.train_job:train_job_flow",
            "path": "",
        },
        {
            "deployment_name": "train-and-predict-deployment",
            "flow_name": "training-train-and-predict",
            "work_pool_name": "default-gpu",
            "entrypoint": "app.modules.training.flows.train_predict:train_and_predict_flow",
            "path": "",
        },
        {
            "deployment_name": "predict-job-batch-deployment",
            "flow_name": "prediction-predict-job",
            "work_pool_name": "default-gpu",
            "entrypoint": "app.modules.prediction.flows.predict_job:predict_job_flow",
            "path": "",
        },
        {
            "deployment_name": "embed-job-batch-deployment",
            "flow_name": "embedding-embed",
            "work_pool_name": "default-gpu",
            "entrypoint": "app.modules.embedding.flows.embed:embed_flow",
            "path": "",
        },
        # ── CPU pool ──
        {
            "deployment_name": "timer-sensor",
            "flow_name": "timer-sensor",
            "work_pool_name": "default-cpu",
            "entrypoint": "app.modules.sensors.adapter.flows.timer_sensor:timer_sensor",
            "path": "",
        },
        {
            "deployment_name": "dataset-size-sensor",
            "flow_name": "dataset-size-sensor",
            "work_pool_name": "default-cpu",
            "entrypoint": "app.modules.sensors.adapter.flows.dataset_size_sensor:dataset_size_sensor",
            "path": "",
        },
        {
            "deployment_name": "drain-dataset",
            "flow_name": "drain-dataset",
            "work_pool_name": "default-cpu",
            "entrypoint": "app.modules.datasets.adapter.flows.drain_dataset:drain_dataset",
            "path": "",
        },
    ]

    for dep in deployments:
        try:
            await prefect_client.ensure_deployment(
                deployment_name=dep["deployment_name"],
                flow_name=dep["flow_name"],
                work_pool_name=dep["work_pool_name"],
                entrypoint=dep.get("entrypoint"),
                path=dep.get("path"),
            )
        except Exception:
            _logger.warning(
                "Failed to ensure deployment '%s'",
                dep["deployment_name"],
                exc_info=True,
            )


@asynccontextmanager
async def lifespan(api: FastAPI):
    cfg = load_config()
    init_logging(cfg)
    ctx = build_app_context(cfg)
    api.state.app_context = ctx

    # ── Startup readiness checks ─────────────────────────────────────────────
    # Fail fast if stateful dependencies are not reachable.  The container
    # orchestrator (Compose / Kubernetes) should restart the pod after a delay.
    # ──────────────────────────────────────────────────────────────────────

    # 1. Postgres
    try:
        async with ctx.shared.db_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        _logger.info("Readiness check passed: postgres")
    except Exception:
        _logger.error("Readiness check failed: postgres unreachable", exc_info=True)
        sys.exit(1)

    # 2. Redis-backed metrics + event publishing (best effort)
    import redis.asyncio as redis_client  # type: ignore[import-untyped]

    metrics_redis: Any | None = None
    try:
        metrics_redis = redis_client.Redis(
            host=str(cfg.redis.host),
            port=int(cfg.redis.port),
            password=str(cfg.redis.password) if cfg.redis.password else None,
            db=int(cfg.redis.db),
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        await metrics_redis.ping()  # type: ignore[awaitable]
        online_jwt_users.configure_redis(metrics_redis)

        ctx.shared.redis_event_publisher = RedisEventPublisher(metrics_redis)
        _logger.info("Metrics Redis + event publisher configured")
    except Exception:
        if metrics_redis is not None:
            await metrics_redis.aclose()
        online_jwt_users.configure_redis(None)
        ctx.shared.redis_event_publisher = RedisEventPublisher(None)
        _logger.warning(
            "Metrics Redis unavailable; falling back to per-process counters"
        )

    # 3. Label Studio
    ls_url = str(cfg.label_studio.url)
    if ls_url:
        try:
            import urllib.request

            urllib.request.urlopen(f"{ls_url}/health", timeout=5)
            _logger.info("Readiness check passed: label-studio")
        except Exception:
            _logger.error(
                "Readiness check failed: label-studio unreachable", exc_info=True
            )
            sys.exit(1)

    if bool(cfg.db.auto_create):
        await init_db(ctx.shared.db_engine)

    if not bool(getattr(cfg.auth, "enabled", True)):
        _logger.info("auth disabled — seeding dev user on startup")
        await seed_dev_auth_context(ctx.shared.session_factory)

    if ctx.sensors is None:
        raise RuntimeError("AppContext sensors module was not initialized")

    try:
        sensor_count = ctx.sensors.sensor_registry.load()
    except Exception:
        sensor_count = 0
    _logger.info("Sensor registry: %d sensors loaded", sensor_count)

    try:
        await _ensure_prefect_deployments(cfg, ctx.shared.prefect_client)
    except Exception:
        _logger.warning("Failed to ensure Prefect deployments", exc_info=True)

    try:
        yield
    finally:
        await online_jwt_users.close()
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
        async with (
            request.app.state.app_context.shared.db_engine.connect() as connection
        ):
            await connection.execute(text("SELECT 1"))
    except Exception:
        _logger.warning("Readiness check failed: database unavailable", exc_info=True)
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
