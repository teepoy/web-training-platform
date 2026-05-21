from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.modules.schedules.application.services.scheduler import SchedulerService


def get_scheduler_service(request: Request) -> SchedulerService:
    container = request.app.state.container
    return SchedulerService(
        prefect_client=container.prefect_client,
        repository=container.task_tracker_repository,
    )


SchedulerServiceDep = Annotated[SchedulerService, Depends(get_scheduler_service)]
