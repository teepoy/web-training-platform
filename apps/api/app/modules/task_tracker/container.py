from __future__ import annotations

from dataclasses import dataclass

from app.shared.context import SharedInfra
from app.shared.db.sql_repository import SqlRepository
from app.modules.task_tracker.app.services.task_tracker import TaskTrackerService
from app.modules.task_tracker.port.task_tracker_port import TaskTrackerPort


@dataclass
class TaskTrackerContext:
    task_tracker_repository: SqlRepository
    task_tracker_port: TaskTrackerPort
    task_tracker_service: TaskTrackerService


def init_task_tracker(shared: SharedInfra) -> TaskTrackerContext:
    repo = SqlRepository(session_factory=shared.session_factory)
    svc = TaskTrackerService(
        repository=repo,
        prefect_client=shared.prefect_client,
        config=shared.config,
    )
    return TaskTrackerContext(
        task_tracker_repository=repo,
        task_tracker_port=repo,
        task_tracker_service=svc,
    )
