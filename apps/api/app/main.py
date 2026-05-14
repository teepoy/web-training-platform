from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import get_current_org, get_current_user
from app.api.schemas import (
    DashboardResponse,
    JobQueueStats,
    RecentJobSummary,
    ServiceStatus,
    WorkPoolStatus,
)
from app.container import Container
from app.db.models import OrganizationORM
from app.db.session import init_db
from app.domain.models import DEFAULT_ORG_ID, Organization, User
from app.routers.registry import EXTENSION_ROUTERS, DOMAIN_ROUTERS

_logger = logging.getLogger(__name__)


async def _sync_file_presets_to_db() -> None:
    registry = container.preset_registry()
    repo = container.repository()
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


@asynccontextmanager
async def lifespan(_: FastAPI):
    cfg = container.config()
    if bool(cfg.db.auto_create):
        await init_db(container.db_engine())

    registry = container.preset_registry()
    count = registry.load()
    _logger.info("Preset registry: %d presets loaded", count)
    await _sync_file_presets_to_db()

    yield


app = FastAPI(title="Online Finetune API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

container = Container()

for r in EXTENSION_ROUTERS:
    app.include_router(r)
for r in DOMAIN_ROUTERS:
    app.include_router(r)


# ---------------------------------------------------------------------------
# Core endpoints not belonging to a single domain
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, str | bool]:
    cfg = container.config()
    return {
        "status": "ok",
        "auth_enabled": bool(getattr(cfg.auth, "enabled", True)),
    }


@app.get("/api/v1/health")
def api_health() -> dict[str, str | bool]:
    return health()


@app.get("/api/v1/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> DashboardResponse:
    repo = container.repository()
    cfg = container.config()
    service_health = container.service_health()

    all_jobs = await repo.list_jobs(org_id=org.id)
    stats = JobQueueStats()
    for j in all_jobs:
        s = j.status.value if hasattr(j.status, "value") else str(j.status)
        if s == "queued":
            stats.queued += 1
        elif s == "running":
            stats.running += 1
        elif s == "completed":
            stats.completed += 1
        elif s == "failed":
            stats.failed += 1
        elif s == "cancelled":
            stats.cancelled += 1

    sorted_jobs = sorted(all_jobs, key=lambda j: j.created_at, reverse=True)[:20]
    recent: list[RecentJobSummary] = [
        RecentJobSummary(
            id=j.id,
            dataset_id=j.dataset_id,
            preset_id=j.preset_id,
            status=j.status.value if hasattr(j.status, "value") else str(j.status),
            created_by=j.created_by,
            created_at=j.created_at
            if isinstance(j.created_at, str)
            else j.created_at.isoformat(),
            updated_at=j.updated_at
            if isinstance(j.updated_at, str)
            else j.updated_at.isoformat(),
        )
        for j in sorted_jobs
    ]

    work_pool: WorkPoolStatus | None = None
    prefect_connected = False
    engine_name = str(cfg.execution.engine)

    if engine_name == "prefect":
        pool_name = str(cfg.prefect.work_pool_name)
        try:
            prefect_client = container.prefect_client()
            pool_data = await prefect_client.get_work_pool(pool_name)
            prefect_connected = True

            slots_used = 0
            try:
                running_runs = await prefect_client.filter_flow_runs(
                    work_pool_name=pool_name,
                    state_types=["RUNNING"],
                )
                slots_used = len(running_runs)
            except Exception:
                pass

            work_pool = WorkPoolStatus(
                name=pool_data.get("name", pool_name),
                type=pool_data.get("type", "unknown"),
                is_paused=pool_data.get("is_paused", False),
                concurrency_limit=pool_data.get("concurrency_limit"),
                slots_used=slots_used,
                status="paused" if pool_data.get("is_paused", False) else "ready",
            )
        except Exception:
            pass

    services = [
        ServiceStatus.model_validate(item.model_dump())
        for item in await service_health.check_all()
    ]

    return DashboardResponse(
        work_pool=work_pool,
        job_queue=stats,
        recent_jobs=recent,
        services=services,
        prefect_connected=prefect_connected,
    )
