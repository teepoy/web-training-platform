from __future__ import annotations

from dataclasses import dataclass

from app.shared.context import SharedInfra
from app.shared.db.sql_repository import SqlRepository

from app.modules.schedules.app.services.scheduler import SchedulerService


@dataclass
class SchedulesContext:
    scheduler_service: SchedulerService


def init_schedules(
    shared: SharedInfra,
    task_tracker_repository: SqlRepository,
) -> SchedulesContext:
    svc = SchedulerService(
        prefect_client=shared.prefect_client,
        repository=task_tracker_repository,
    )
    return SchedulesContext(scheduler_service=svc)
