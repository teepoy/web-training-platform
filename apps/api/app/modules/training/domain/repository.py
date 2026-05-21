from __future__ import annotations

from typing import Protocol

from app.shared.api.schemas import ArtifactRef, JobStatus, TrainingEvent, TrainingJob


class TrainingRepository(Protocol):
    async def create_job(self, job: TrainingJob) -> TrainingJob: ...

    async def get_job(
        self,
        job_id: str,
        org_id: str | None = None,
    ) -> TrainingJob | None: ...

    async def set_job_external_id(self, job_id: str, external_job_id: str) -> None: ...

    async def get_job_external_id(self, job_id: str) -> str | None: ...

    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        summary: dict | None = None,
    ) -> None: ...

    async def add_event(self, event: TrainingEvent) -> None: ...

    async def add_artifacts(
        self,
        job_id: str,
        artifacts: list[ArtifactRef],
    ) -> None: ...

    async def did_user_leave(self, job_id: str) -> bool: ...
