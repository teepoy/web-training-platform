from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.routing import compile_path

from app.composition import build_app_context
from app.modules.auth.port.http.deps import (
    get_current_org,
    get_current_user,
    seed_dev_auth_context,
)
from app.modules.dashboard.port.http.deps import DashboardServiceDep
from app.shared.api.schemas import (
    DashboardResponse,
)
from app.core.config import load_config
from app.shared.db.session import init_db
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
            "deployment_name": "sc-import-deployment",
            "flow_name": "sc-import-upstream",
            "work_pool_name": "default-cpu",
            "entrypoint": "app.modules.sc.adapter.flows.sc_import:sc_import",
            "path": "",
        },
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
    ctx = build_app_context(cfg)
    api.state.app_context = ctx

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

for r in [*MODULE_ROUTERS, *EXTENSION_ROUTERS]:
    _strip_api_prefix(r)
    app.include_router(r, prefix="/api/v1")


# ---------------------------------------------------------------------------
# Core endpoints not belonging to a single domain
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
