from __future__ import annotations

from typing import Protocol

from app.shared.api.schemas import (
    ArtifactRef,
    JobStatus,
    TrainingEvent,
    TrainingJob,
)


class TrainingRepository(Protocol):
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
    ) -> list[TrainingJob]: ...

    async def list_jobs_paginated(
        self,
        org_id: str | None = None,
        dataset_id: str | None = None,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[TrainingJob], int]: ...

    async def set_job_external_id(self, job_id: str, external_job_id: str) -> None: ...

    async def get_job_external_id(self, job_id: str) -> str | None: ...

    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        summary: dict | None = None,
    ) -> None: ...

    async def add_event(self, event: TrainingEvent) -> None: ...

    async def list_events(self, job_id: str) -> list[TrainingEvent]: ...

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

    async def mark_user_left(self, job_id: str) -> bool: ...

    async def did_user_leave(self, job_id: str) -> bool: ...

    async def set_job_public(self, job_id: str, is_public: bool) -> bool: ...
