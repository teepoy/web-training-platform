from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.config import AppConfig
from app.shared.api.schemas import (
    DashboardResponse,
    JobQueueStats,
    RecentJobSummary,
    ServiceStatus,
    WorkPoolStatus,
)
from app.shared.api.schemas import Organization, User
from app.modules.dashboard.port.local import ServiceHealthPort
from app.modules.auth.port.http.deps import (
    get_current_org,
    get_current_user,
)
from app.modules.dashboard.port.http.deps import (
    get_config,
    get_prefect_client,
    get_repository,
    get_service_health,
)
from app.shared.domain.protocols import PrefectClient
from app.shared.infrastructure.prefect.deployments import CONTROL_PLANE_WORK_POOL_NAME
from app.modules.jobs.task_tracker.port.task_tracker_port import TaskTrackerPort

router = APIRouter(prefix="/api/v1", tags=["dashboard"])


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    operation_id="get_dashboard_module_api_v1_dashboard_get",
)
async def get_dashboard(
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: TaskTrackerPort = Depends(get_repository),
    cfg: AppConfig = Depends(get_config),
    service_health: ServiceHealthPort = Depends(get_service_health),
    prefect_client: PrefectClient = Depends(get_prefect_client),
) -> DashboardResponse:
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
            trainer_id=j.trainer_id,
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
        pool_name = CONTROL_PLANE_WORK_POOL_NAME
        try:
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
