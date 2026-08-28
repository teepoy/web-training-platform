from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from app.shared.api.schemas import (
    ArtifactRef,
    JobStatus,
    TrainingEvent,
    TrainingJob,
)


@dataclass(frozen=True, slots=True)
class ActiveTrainingExecution:
    job_id: str
    external_job_id: str
    status: JobStatus


TrainingJobSortField = Literal["created_at", "updated_at", "status", "creator"]
SortDirection = Literal["asc", "desc"]


class TrainingRepository(Protocol):
    async def has_active_jobs(self, *, dataset_id: str, org_id: str) -> bool: ...

    async def create_job(self, job: TrainingJob) -> TrainingJob: ...

    async def get_job(
        self,
        job_id: str,
        org_id: str | None = None,
    ) -> TrainingJob | None: ...

    async def list_jobs(
        self,
        org_id: str | None = None,
        dataset_id: str | None = None,
        *,
        include_artifacts: bool = False,
    ) -> list[TrainingJob]: ...

    async def list_jobs_paginated(
        self,
        org_id: str | None = None,
        dataset_id: str | None = None,
        *,
        offset: int = 0,
        limit: int = 50,
        include_artifacts: bool = True,
        query: str | None = None,
        status: JobStatus | None = None,
        creator_id: str | None = None,
        sort_by: TrainingJobSortField = "created_at",
        sort_order: SortDirection = "desc",
    ) -> tuple[list[TrainingJob], int]: ...

    async def set_job_external_id(self, job_id: str, external_job_id: str) -> None: ...

    async def get_job_external_id(
        self,
        job_id: str,
        org_id: str | None = None,
    ) -> str | None: ...

    async def list_active_executions(self) -> list[ActiveTrainingExecution]: ...

    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
    ) -> bool: ...

    async def add_event(self, event: TrainingEvent) -> None: ...

    async def list_events(self, job_id: str) -> list[TrainingEvent]: ...

    async def list_events_after(
        self,
        job_id: str,
        after_id: int,
        limit: int = 200,
    ) -> tuple[list[TrainingEvent], int]: ...

    async def list_events_paginated(
        self,
        job_id: str,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[TrainingEvent], int]: ...

    async def add_artifacts(
        self,
        job_id: str,
        artifacts: list[ArtifactRef],
    ) -> None: ...

    async def upsert_artifacts(
        self,
        job_id: str,
        artifacts: list[ArtifactRef],
    ) -> None: ...

    async def mark_user_left(self, job_id: str) -> bool: ...

    async def did_user_leave(self, job_id: str) -> bool: ...

    async def set_job_public(self, job_id: str, is_public: bool) -> bool: ...
