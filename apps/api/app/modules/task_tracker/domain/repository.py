from __future__ import annotations

from typing import Protocol

from app.shared.api.schemas import (
    JobStatus,
    PredictionEvent,
    PredictionJob,
    TrainingEvent,
    TrainingJob,
)
from app.shared.db.models.schedules import ScheduleORM


class TaskTrackerRepository(Protocol):
    async def list_jobs(self, org_id: str | None = None) -> list[TrainingJob]: ...

    async def get_job(
        self, job_id: str, org_id: str | None = None
    ) -> TrainingJob | None: ...

    async def list_dataset_names(
        self, dataset_ids: list[str], org_id: str | None = None
    ) -> dict[str, str]: ...

    async def get_job_external_id(self, job_id: str) -> str | None: ...

    async def update_job_status(self, job_id: str, status: JobStatus) -> None: ...

    async def list_prediction_jobs(
        self, org_id: str | None = None
    ) -> list[PredictionJob]: ...

    async def get_prediction_job(
        self, job_id: str, org_id: str | None = None
    ) -> PredictionJob | None: ...

    async def update_prediction_job_status(
        self, job_id: str, status: JobStatus
    ) -> None: ...

    async def list_schedules(self, org_id: str) -> list[ScheduleORM]: ...

    async def list_events(self, job_id: str) -> list[TrainingEvent]: ...

    async def list_prediction_events(self, job_id: str) -> list[PredictionEvent]: ...

    async def add_event(self, event: TrainingEvent) -> None: ...

    async def set_job_external_id(self, job_id: str, external_job_id: str) -> None: ...
