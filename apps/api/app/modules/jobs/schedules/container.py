from __future__ import annotations

from dataclasses import dataclass

from app.modules.jobs.schedules.adapter.repositories.repository import (
    ScheduleSqlRepository,
)
from app.shared.context import SharedInfra

from app.modules.jobs.schedules.app.services.scheduler import SchedulerService
from app.modules.jobs.schedules.domain.repository import ScheduleRepository


@dataclass
class SchedulesContext:
    schedule_repository: ScheduleRepository
    scheduler_service: SchedulerService


def init_schedules(shared: SharedInfra) -> SchedulesContext:
    schedule_repository = ScheduleSqlRepository(
        session_factory=shared.session_factory.sessionmaker
    )
    svc = SchedulerService(
        prefect_client=shared.prefect_client,
        repository=schedule_repository,
    )
    return SchedulesContext(
        schedule_repository=schedule_repository,
        scheduler_service=svc,
    )
