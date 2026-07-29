from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.modules.jobs.schedules.port.local import ScheduleManagementPort
from app.shared.injection import resolve


def get_scheduler_service(request: Request) -> ScheduleManagementPort:
    return resolve(request, ScheduleManagementPort)


SchedulerServiceDep = Annotated[ScheduleManagementPort, Depends(get_scheduler_service)]
