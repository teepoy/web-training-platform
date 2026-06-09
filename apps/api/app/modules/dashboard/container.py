from __future__ import annotations

from dataclasses import dataclass

from app.modules.dashboard.app.dashboard_service import DashboardService
from app.modules.dashboard.app.services.service_health import ServiceHealthService
from app.modules.task_tracker.port.task_tracker_port import TaskTrackerPort
from app.shared.context import SharedInfra


@dataclass
class DashboardContext:
    dashboard_service: DashboardService
    service_health_service: ServiceHealthService
    task_tracker_port: TaskTrackerPort


def init_dashboard(
    shared: SharedInfra,
    task_tracker_port: TaskTrackerPort,
) -> DashboardContext:
    service_health = ServiceHealthService(
        config=shared.config,
        prefect_client=shared.prefect_client,
    )
    dashboard_service = DashboardService(
        job_repository=task_tracker_port,
        service_health=service_health,
        prefect_client=shared.prefect_client,
        config=shared.config,
    )
    return DashboardContext(
        dashboard_service=dashboard_service,
        service_health_service=service_health,
        task_tracker_port=task_tracker_port,
    )
