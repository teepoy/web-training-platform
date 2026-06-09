from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from omegaconf import DictConfig

from app.modules.dashboard.app.dashboard_service import DashboardService
from app.modules.dashboard.app.services.service_health import (
    ServiceHealthService,
)
from app.modules.task_tracker.port.task_tracker_port import TaskTrackerPort
from app.shared.domain.protocols import PrefectClient


def get_dashboard_service(request: Request) -> DashboardService:
    return request.app.state.app_context.dashboard.dashboard_service


def get_repository(request: Request) -> TaskTrackerPort:
    return request.app.state.app_context.dashboard.task_tracker_port


def get_config(request: Request) -> DictConfig:
    return request.app.state.app_context.shared.config


def get_service_health(request: Request) -> ServiceHealthService:
    return request.app.state.app_context.dashboard.service_health_service


def get_prefect_client(request: Request) -> PrefectClient:
    return request.app.state.app_context.shared.prefect_client


DashboardServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]
