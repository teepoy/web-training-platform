from __future__ import annotations

from fastapi import Request

from app.core.config import AppConfig
from app.modules.jobs.task_tracker.port.task_tracker_port import (
    TaskTrackerServicePort,
)
from app.shared.domain.protocols import PrefectClient
from app.shared.injection import resolve


def get_prefect_client(request: Request) -> PrefectClient:
    return resolve(request, PrefectClient)


def get_config(request: Request) -> AppConfig:
    return resolve(request, AppConfig)


def get_task_tracker_service(request: Request) -> TaskTrackerServicePort:
    return resolve(request, TaskTrackerServicePort)
