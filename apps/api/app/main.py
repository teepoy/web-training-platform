from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.routing import compile_path

from app.composition import AppContainer, build_app_container
from app.modules.auth.interfaces.controllers.deps import (
    get_current_org,
    get_current_user,
)
from app.modules.dashboard.api.deps import DashboardServiceDep
from app.shared.api.schemas import (
    DashboardResponse,
)
from app.core.config import load_config
from app.shared.db.registry import OrganizationORM
from app.shared.db.session import init_db
from app.shared.db.sql_repository import SqlRepository
from app.shared.api.schemas import DEFAULT_ORG_ID, Organization, User
from app.modules.registry import EXTENSION_ROUTERS, MODULE_ROUTERS

_logger = logging.getLogger(__name__)


def _build_state_container(api: FastAPI, cfg: Any) -> AppContainer:
    container = build_app_container(cfg)
    api.state.container = container
    return container


async def _sync_file_presets_to_db(container: AppContainer) -> None:
    registry = container.preset_registry
    repo = container.prediction_repository
    if not isinstance(repo, SqlRepository):
        raise TypeError("Prediction repository is not a SqlRepository")
    existing_default_org = await repo.get_organization(DEFAULT_ORG_ID)
    if existing_default_org is None:
        await repo.create_organization(
            OrganizationORM(
                id=DEFAULT_ORG_ID,
                name="Default",
                slug="default",
            )
        )
    existing = await repo.list_preset_ids()
    for spec in registry.list_presets():
        if spec.id in existing:
            continue
        legacy = registry.preset_to_api_dict(spec)
        await repo.ensure_preset_row(
            preset_id=spec.id,
            name=spec.name,
            model_spec=legacy.get("model_spec", {})
            if isinstance(legacy.get("model_spec", {}), dict)
            else {},
            omegaconf_yaml=str(legacy.get("omegaconf_yaml", "")),
            dataloader_ref=str(legacy.get("dataloader_ref", "")),
        )


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
    container = _build_state_container(api, cfg)
    import app.modules.prediction.infrastructure.flows.predict_job as _predict_job_mod
    import app.modules.training.infrastructure.flows.train_job as _train_job_mod

    _predict_job_mod._app_container_ref = container
    _train_job_mod._app_container_ref = container
    if bool(cfg.db.auto_create):
        await init_db(container.db_engine)

    registry = container.preset_registry
    count = registry.load()
    _logger.info("Preset registry: %d presets loaded", count)
    try:
        sensor_count = container.sensor_registry.load()
    except Exception:
        sensor_count = 0
    _logger.info("Sensor registry: %d sensors loaded", sensor_count)
    await _sync_file_presets_to_db(container)

    try:
        yield
    finally:
        _predict_job_mod._app_container_ref = None
        _train_job_mod._app_container_ref = None
        await container.close()


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
def health() -> dict[str, str | bool]:
    cfg = (
        app.state.container.config if hasattr(app.state, "container") else load_config()
    )
    return {
        "status": "ok",
        "auth_enabled": bool(getattr(cfg.auth, "enabled", True)),
    }


@app.get("/api/v1/health")
def api_health() -> dict[str, str | bool]:
    return health()


@app.get("/api/v1/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    service: DashboardServiceDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> DashboardResponse:
    return await service.get_dashboard_data(org_id=org.id)
