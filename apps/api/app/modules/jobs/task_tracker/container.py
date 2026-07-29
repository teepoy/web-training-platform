from __future__ import annotations

from dataclasses import dataclass

from app.modules.datasets.domain.repository import DatasetRepository
from app.modules.prediction.domain.repository import PredictionRepository
from app.shared.context import SharedInfra
from app.modules.jobs.task_tracker.app.services.task_tracker import TaskTrackerService
from app.modules.jobs.task_tracker.port.task_tracker_port import TaskTrackerPort
from app.modules.training.domain.repository import TrainingRepository
from app.modules.jobs.schedules.port.local import ScheduleManagementPort


@dataclass
class TaskTrackerContext:
    task_tracker_port: TaskTrackerPort
    task_tracker_service: TaskTrackerService


def init_task_tracker(
    shared: SharedInfra,
    *,
    training_repository: TrainingRepository,
    prediction_repository: PredictionRepository,
    dataset_repository: DatasetRepository,
    schedule_run_reader: ScheduleManagementPort,
) -> TaskTrackerContext:
    svc = TaskTrackerService(
        training_repository=training_repository,
        prediction_repository=prediction_repository,
        dataset_repository=dataset_repository,
        prefect_client=shared.prefect_client,
        config=shared.config,
        schedule_run_reader=schedule_run_reader,
    )
    return TaskTrackerContext(
        task_tracker_port=training_repository,
        task_tracker_service=svc,
    )
