from __future__ import annotations

from typing import Any

from app.modules.dashboard.application.services.service_health import (
    ServiceHealthService,
)
from app.modules.dashboard.domain.protocols import JobRepository
from app.shared.api.schemas import (
    DashboardResponse,
    JobQueueStats,
    RecentJobSummary,
    ServiceStatus,
    WorkPoolStatus,
)
from app.shared.domain.protocols import PrefectClient


class DashboardService:
    def __init__(
        self,
        job_repository: JobRepository,
        service_health: ServiceHealthService,
        prefect_client: PrefectClient,
        config: Any,
    ) -> None:
        self._job_repository = job_repository
        self._service_health = service_health
        self._prefect_client = prefect_client
        self._config = config

    async def get_dashboard_data(self, org_id: str) -> DashboardResponse:
        all_jobs = await self._job_repository.list_jobs(org_id=org_id)
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
        engine_name = str(self._config.execution.engine)

        if engine_name == "prefect":
            pool_name = str(self._config.prefect.work_pool_name)
            try:
                pool_data = await self._prefect_client.get_work_pool(pool_name)
                prefect_connected = True

                slots_used = 0
                try:
                    running_runs = await self._prefect_client.filter_flow_runs(
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
            for item in await self._service_health.check_all()
        ]

        return DashboardResponse(
            work_pool=work_pool,
            job_queue=stats,
            recent_jobs=recent,
            services=services,
            prefect_connected=prefect_connected,
        )
