from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.modules.dashboard.application.dashboard_service import DashboardService


def get_dashboard_service(request: Request) -> DashboardService:
    container = request.app.state.container
    return DashboardService(
        job_repository=container.task_tracker_repository,
        service_health=container.service_health_service,
        prefect_client=container.prefect_client,
        config=container.config,
    )


DashboardServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]
