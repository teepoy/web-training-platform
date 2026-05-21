from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from omegaconf import DictConfig  # pyright: ignore[reportMissingImports]

from app.modules.dashboard.application.dashboard_service import DashboardService
from app.modules.dashboard.application.services.service_health import (
    ServiceHealthService,
)
from app.shared.db.sql_repository import SqlRepository
from app.shared.domain.protocols import PrefectClient


def get_dashboard_service(request: Request) -> DashboardService:
    container = request.app.state.container
    return DashboardService(
        job_repository=container.task_tracker_repository,
        service_health=container.service_health_service,
        prefect_client=container.prefect_client,
        config=container.config,
    )


def get_repository(request: Request) -> SqlRepository:
    return request.app.state.container.task_tracker_repository


def get_config(request: Request) -> DictConfig:
    return request.app.state.container.config


def get_service_health(request: Request) -> ServiceHealthService:
    return request.app.state.container.service_health_service


def get_prefect_client(request: Request) -> PrefectClient:
    return request.app.state.container.prefect_client


DashboardServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]
