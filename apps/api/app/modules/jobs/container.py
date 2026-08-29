from __future__ import annotations

from dataclasses import dataclass

from injector import Module, inject, provider, singleton

from app.modules.datasets.domain.repository import DatasetRepository
from app.modules.jobs.schedules.app.services.scheduler import SchedulerService
from app.modules.jobs.schedules.container import SchedulesContext, init_schedules
from app.modules.jobs.schedules.domain.repository import ScheduleRepository
from app.modules.jobs.schedules.port.local import ScheduleManagementPort
from app.modules.jobs.task_tracker.app.services.task_tracker import TaskTrackerService
from app.modules.jobs.task_tracker.container import (
    TaskTrackerContext,
    init_task_tracker,
)
from app.modules.jobs.task_tracker.port.task_tracker_port import (
    TaskTrackerPort,
    TaskTrackerServicePort,
)
from app.modules.prediction.domain.repository import PredictionRepository
from app.modules.training.domain.repository import TrainingRepository
from app.shared.context import SharedInfra


@dataclass
class JobsContext:
    schedules: SchedulesContext
    task_tracker: TaskTrackerContext


def init_jobs(
    shared: SharedInfra,
    *,
    training_repository: TrainingRepository,
    prediction_repository: PredictionRepository,
    dataset_repository: DatasetRepository,
) -> JobsContext:
    schedules = init_schedules(shared)
    task_tracker = init_task_tracker(
        shared,
        training_repository=training_repository,
        prediction_repository=prediction_repository,
        dataset_repository=dataset_repository,
        schedule_run_reader=schedules.scheduler_service,
    )
    return JobsContext(
        schedules=schedules,
        task_tracker=task_tracker,
    )


class JobsModule(Module):
    @inject
    @provider
    @singleton
    def provide_jobs_context(
        self,
        shared: SharedInfra,
        training_repository: TrainingRepository,
        prediction_repository: PredictionRepository,
        dataset_repository: DatasetRepository,
    ) -> JobsContext:
        return init_jobs(
            shared,
            training_repository=training_repository,
            prediction_repository=prediction_repository,
            dataset_repository=dataset_repository,
        )

    @provider
    @singleton
    def provide_schedules_context(self, context: JobsContext) -> SchedulesContext:
        return context.schedules

    @provider
    @singleton
    def provide_schedule_repository(
        self, schedules: SchedulesContext
    ) -> ScheduleRepository:
        return schedules.schedule_repository

    @provider
    @singleton
    def provide_scheduler_service(
        self, schedules: SchedulesContext
    ) -> SchedulerService:
        return schedules.scheduler_service

    @provider
    @singleton
    def provide_schedule_management(
        self, schedules: SchedulesContext
    ) -> ScheduleManagementPort:
        return schedules.scheduler_service

    @provider
    @singleton
    def provide_task_tracker_context(self, context: JobsContext) -> TaskTrackerContext:
        return context.task_tracker

    @provider
    @singleton
    def provide_task_tracker_port(
        self, task_tracker: TaskTrackerContext
    ) -> TaskTrackerPort:
        return task_tracker.task_tracker_port

    @provider
    @singleton
    def provide_task_tracker_service(
        self, task_tracker: TaskTrackerContext
    ) -> TaskTrackerService:
        return task_tracker.task_tracker_service

    @provider
    @singleton
    def provide_task_tracker_service_port(
        self, service: TaskTrackerService
    ) -> TaskTrackerServicePort:
        return service
