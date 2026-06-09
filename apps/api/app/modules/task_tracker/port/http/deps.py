from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Request

from app.modules.task_tracker.app.services.task_tracker import (
    TaskTrackerService,
)
from app.modules.task_tracker.domain.repository import TaskTrackerRepository
from app.shared.domain.protocols import PrefectClient


def get_task_tracker_repository(request: Request) -> TaskTrackerRepository:
    return request.app.state.app_context.task_tracker.task_tracker_repository


def get_prefect_client(request: Request) -> PrefectClient:
    return request.app.state.app_context.shared.prefect_client


def get_config(request: Request) -> Any:
    return request.app.state.app_context.shared.config


def get_task_tracker_service(
    repository: Annotated[TaskTrackerRepository, Depends(get_task_tracker_repository)],
    prefect_client: Annotated[PrefectClient, Depends(get_prefect_client)],
    config: Annotated[Any, Depends(get_config)],
) -> TaskTrackerService:
    return TaskTrackerService(
        repository=repository,
        prefect_client=prefect_client,
        config=config,
    )
