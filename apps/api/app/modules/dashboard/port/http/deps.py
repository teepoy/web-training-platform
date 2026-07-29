from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.core.config import AppConfig
from app.modules.dashboard.port.local import DashboardQueryPort, ServiceHealthPort
from app.modules.jobs.task_tracker.port.task_tracker_port import TaskTrackerPort
from app.shared.domain.protocols import PrefectClient
from app.shared.injection import resolve


def get_dashboard_service(request: Request) -> DashboardQueryPort:
    return resolve(request, DashboardQueryPort)


def get_repository(request: Request) -> TaskTrackerPort:
    return resolve(request, TaskTrackerPort)


def get_config(request: Request) -> AppConfig:
    return resolve(request, AppConfig)


def get_service_health(request: Request) -> ServiceHealthPort:
    return resolve(request, ServiceHealthPort)


def get_prefect_client(request: Request) -> PrefectClient:
    return resolve(request, PrefectClient)


DashboardServiceDep = Annotated[DashboardQueryPort, Depends(get_dashboard_service)]
