from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.modules.schedules.app.services.scheduler import SchedulerService


def get_scheduler_service(request: Request) -> SchedulerService:
    return request.app.state.app_context.schedules.scheduler_service


SchedulerServiceDep = Annotated[SchedulerService, Depends(get_scheduler_service)]
