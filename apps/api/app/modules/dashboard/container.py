from __future__ import annotations

from dataclasses import dataclass

from injector import Module, inject, provider, singleton

from app.modules.dashboard.app.dashboard_service import DashboardService
from app.modules.dashboard.app.services.service_health import ServiceHealthService
from app.modules.dashboard.domain.protocols import JobRepository
from app.modules.dashboard.port.local import DashboardQueryPort, ServiceHealthPort
from app.modules.jobs.task_tracker.port.task_tracker_port import TaskTrackerPort
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


class DashboardModule(Module):
    @inject
    @provider
    @singleton
    def provide_dashboard_context(
        self,
        shared: SharedInfra,
        task_tracker_port: TaskTrackerPort,
    ) -> DashboardContext:
        return init_dashboard(
            shared,
            task_tracker_port=task_tracker_port,
        )

    @provider
    @singleton
    def provide_service_health(self, context: DashboardContext) -> ServiceHealthService:
        return context.service_health_service

    @provider
    @singleton
    def provide_service_health_port(
        self, service: ServiceHealthService
    ) -> ServiceHealthPort:
        return service

    @provider
    @singleton
    def provide_dashboard_job_repository(
        self, context: DashboardContext
    ) -> JobRepository:
        return context.task_tracker_port

    @provider
    @singleton
    def provide_dashboard_service(self, context: DashboardContext) -> DashboardService:
        return context.dashboard_service

    @provider
    @singleton
    def provide_dashboard_query(self, service: DashboardService) -> DashboardQueryPort:
        return service
